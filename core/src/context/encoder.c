#define _POSIX_C_SOURCE 200809L
#include "recursant/encoder.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef RECURSANT_WITH_ENCODER
struct rc_encoder { int unused; };
rc_encoder *rc_encoder_load(const char *model, const char *vocab, int threads, char *err, size_t len) {
    (void)model; (void)vocab; (void)threads;
    if (err && len) snprintf(err, len, "this build has no encoder support (rebuild with -DRECURSANT_ENCODER=ON and libonnxruntime)");
    return NULL;
}
void rc_encoder_free(rc_encoder *enc) { (void)enc; }
size_t rc_encoder_dim(const rc_encoder *enc) { (void)enc; return 0; }
bool rc_encoder_embed(rc_encoder *enc, const char *text, size_t length, float *out) { (void)enc; (void)text; (void)length; (void)out; return false; }
#else
#include <dlfcn.h>
#include <fcntl.h>
#include <pthread.h>
#include <unistd.h>
#include <onnxruntime_c_api.h>

/* ONNX Runtime is loaded with dlopen on first use, so the binary has no link
 * dependency on it and only configs that ask for an encoder need the library.
 * Ubuntu's build registers its ONNX schemas twice and prints a screen of
 * "Schema error" lines while creating the first session; stderr is muted
 * during rc_encoder_load only (encoders load at startup, before worker
 * threads exist; load errors are returned in err, not printed). */
static const OrtApiBase *ort_base;
static pthread_once_t ort_once = PTHREAD_ONCE_INIT;
static void ort_open(void) {
    static const char *names[] = {"libonnxruntime.so.1", "libonnxruntime.so.1.23", "libonnxruntime.so"};
    void *lib = NULL;
    const char *env = getenv("RECURSANT_ONNXRUNTIME");
    if (env && *env) lib = dlopen(env, RTLD_NOW | RTLD_LOCAL);
    for (size_t i = 0; !lib && !(env && *env) && i < sizeof names / sizeof *names; i++) lib = dlopen(names[i], RTLD_NOW | RTLD_LOCAL);
    const OrtApiBase *(*get)(void) = NULL;
    if (lib) *(void **)&get = dlsym(lib, "OrtGetApiBase");
    ort_base = get ? get() : NULL;
}

#define MAX_INPUTS 4
struct rc_encoder {
    const OrtApi *api;
    OrtEnv *env;
    OrtSession *session;
    OrtMemoryInfo *memory;
    rc_wordpiece *wp;
    size_t dim, inputs;
    char *input_names[MAX_INPUTS];
    char *output_name;
};

static bool check(rc_encoder *e, OrtStatus *status, char *err, size_t len) {
    if (!status) return true;
    if (err && len) snprintf(err, len, "onnxruntime: %s", e->api->GetErrorMessage(status));
    e->api->ReleaseStatus(status);
    return false;
}
void rc_encoder_free(rc_encoder *e) {
    if (!e) return;
    for (size_t i = 0; i < e->inputs; i++) free(e->input_names[i]);
    free(e->output_name);
    if (e->api) {
        if (e->memory) e->api->ReleaseMemoryInfo(e->memory);
        if (e->session) e->api->ReleaseSession(e->session);
        if (e->env) e->api->ReleaseEnv(e->env);
    }
    rc_wordpiece_free(e->wp);
    free(e);
}
size_t rc_encoder_dim(const rc_encoder *e) { return e ? e->dim : 0; }

static bool embed(rc_encoder *e, const char *text, size_t length, float *out, size_t *dim);
static rc_encoder *load(const char *model, const char *vocab, int threads, char *err, size_t len);
rc_encoder *rc_encoder_load(const char *model, const char *vocab, int threads, char *err, size_t len) {
    fflush(stderr);
    int saved = dup(STDERR_FILENO), null = open("/dev/null", O_WRONLY | O_CLOEXEC);
    if (saved >= 0 && null >= 0) dup2(null, STDERR_FILENO);
    rc_encoder *e = load(model, vocab, threads, err, len);
    fflush(stderr);
    if (saved >= 0) { dup2(saved, STDERR_FILENO); close(saved); }
    if (null >= 0) close(null);
    return e;
}
static rc_encoder *load(const char *model, const char *vocab, int threads, char *err, size_t len) {
    if (err && len) err[0] = 0;
    rc_encoder *e = calloc(1, sizeof *e);
    if (!e) return NULL;
    pthread_once(&ort_once, ort_open);
    if (!ort_base) { if (err && len) snprintf(err, len, "cannot load libonnxruntime (install it, or set RECURSANT_ONNXRUNTIME to its path)"); free(e); return NULL; }
    e->api = ort_base->GetApi(ORT_API_VERSION);
    if (!e->api) { if (err && len) snprintf(err, len, "libonnxruntime %s is older than the build headers (API %d)", ort_base->GetVersionString(), ORT_API_VERSION); free(e); return NULL; }
    if (!(e->wp = rc_wordpiece_load(vocab))) { if (err && len) snprintf(err, len, "cannot load vocabulary %s", vocab ? vocab : "(null)"); rc_encoder_free(e); return NULL; }
    const OrtApi *a = e->api;
    OrtSessionOptions *so = NULL;
    bool ok = check(e, a->CreateEnv(ORT_LOGGING_LEVEL_ERROR, "recursant", &e->env), err, len) &&
              check(e, a->CreateSessionOptions(&so), err, len) &&
              check(e, a->SetIntraOpNumThreads(so, threads), err, len) &&
              check(e, a->SetInterOpNumThreads(so, 1), err, len) &&
              check(e, a->SetSessionGraphOptimizationLevel(so, ORT_ENABLE_ALL), err, len) &&
              check(e, a->CreateSession(e->env, model, so, &e->session), err, len) &&
              check(e, a->CreateCpuMemoryInfo(OrtArenaAllocator, OrtMemTypeDefault, &e->memory), err, len);
    if (so) a->ReleaseSessionOptions(so);
    OrtAllocator *alloc = NULL; size_t count = 0;
    ok = ok && check(e, a->GetAllocatorWithDefaultOptions(&alloc), err, len) && check(e, a->SessionGetInputCount(e->session, &count), err, len);
    if (ok && (count < 1 || count > MAX_INPUTS)) { ok = false; if (err && len) snprintf(err, len, "encoder model has %zu inputs", count); }
    for (size_t i = 0; ok && i < count; i++) {
        char *name = NULL;
        ok = check(e, a->SessionGetInputName(e->session, i, alloc, &name), err, len);
        if (!ok) break;
        e->input_names[e->inputs++] = strdup(name); alloc->Free(alloc, name);
        const char *n = e->input_names[e->inputs - 1];
        if (!n || (strcmp(n, "input_ids") && strcmp(n, "attention_mask") && strcmp(n, "token_type_ids"))) {
            ok = false; if (err && len) snprintf(err, len, "unsupported encoder input %s", n ? n : "(null)");
        }
    }
    char *out = NULL;
    ok = ok && check(e, a->SessionGetOutputName(e->session, 0, alloc, &out), err, len);
    if (ok) { e->output_name = strdup(out); alloc->Free(alloc, out); ok = e->output_name != NULL; }
    /* Probe once to learn the hidden size (dim is fixed afterwards). */
    float probe[4096];
    if (ok) { e->dim = sizeof probe / sizeof *probe; ok = embed(e, "probe", 5, probe, &e->dim); if (!ok && err && len && !err[0]) snprintf(err, len, "encoder probe failed"); }
    if (!ok) { rc_encoder_free(e); return NULL; }
    return e;
}

static bool embed(rc_encoder *e, const char *text, size_t length, float *out, size_t *dim) {
    if (!e || !e->session || !out) return false;
    const OrtApi *a = e->api;
    int64_t ids[RC_ENCODER_MAX_TOKENS], mask[RC_ENCODER_MAX_TOKENS], types[RC_ENCODER_MAX_TOKENS];
    size_t n = rc_wordpiece_encode(e->wp, text, length, ids, RC_ENCODER_MAX_TOKENS);
    if (!n) return false;
    for (size_t i = 0; i < n; i++) { mask[i] = 1; types[i] = 0; }
    int64_t shape[2] = {1, (int64_t)n};
    OrtValue *in[MAX_INPUTS] = {0}, *result = NULL; bool ok = true;
    for (size_t i = 0; ok && i < e->inputs; i++) {
        int64_t *data = !strcmp(e->input_names[i], "input_ids") ? ids : !strcmp(e->input_names[i], "attention_mask") ? mask : types;
        ok = check(e, a->CreateTensorWithDataAsOrtValue(e->memory, data, n * sizeof *data, shape, 2, ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64, &in[i]), NULL, 0);
    }
    const char *output = e->output_name;
    ok = ok && check(e, a->Run(e->session, NULL, (const char *const *)e->input_names, (const OrtValue *const *)in, e->inputs, &output, 1, &result), NULL, 0);
    float *h = NULL; OrtTensorTypeAndShapeInfo *info = NULL; size_t dims = 0; int64_t out_shape[3] = {0};
    ok = ok && check(e, a->GetTensorMutableData(result, (void **)&h), NULL, 0) &&
         check(e, a->GetTensorTypeAndShape(result, &info), NULL, 0) &&
         check(e, a->GetDimensionsCount(info, &dims), NULL, 0) && dims == 3 &&
         check(e, a->GetDimensions(info, out_shape, 3), NULL, 0);
    if (info) a->ReleaseTensorTypeAndShapeInfo(info);
    size_t hidden = ok ? (size_t)out_shape[2] : 0;
    if (ok && (out_shape[0] != 1 || out_shape[1] != (int64_t)n || !hidden || hidden > *dim)) ok = false;
    if (ok) {
        double norm = 0;
        for (size_t i = 0; i < hidden; i++) norm += (double)h[i] * h[i];   /* [CLS] = row 0 */
        norm = sqrt(norm);
        ok = norm > 0 && isfinite(norm);
        for (size_t i = 0; ok && i < hidden; i++) out[i] = (float)(h[i] / norm);
        *dim = hidden;
    }
    for (size_t i = 0; i < e->inputs; i++) if (in[i]) a->ReleaseValue(in[i]);
    if (result) a->ReleaseValue(result);
    return ok;
}
bool rc_encoder_embed(rc_encoder *e, const char *text, size_t length, float *out) {
    size_t dim = e ? e->dim : 0;
    return e && embed(e, text, length, out, &dim) && dim == e->dim;
}
#endif
