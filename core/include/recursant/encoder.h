#ifndef RECURSANT_ENCODER_H
#define RECURSANT_ENCODER_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
/* Local question encoder for context.prompt (plan Phase 5; evidence
 * docs/evidence/m3-encoder-classifier.md). Two parts:
 *
 * rc_wordpiece: the BERT WordPiece tokenizer of bge-small-en-v1.5, matching the
 * Hugging Face tokenizer.json (BertNormalizer with clean_text, CJK spacing,
 * accent stripping and lowercasing; BertPreTokenizer; WordPiece with "##"
 * continuations, [UNK] for words over 100 characters or with no match;
 * [CLS] ... [SEP]). Character classes come from the generated
 * core/src/context/wordpiece_tables.h. Always built; no dependencies.
 *
 * rc_encoder: ONNX Runtime inference of the encoder, returning the
 * L2-normalized [CLS] embedding. Only built with -DRECURSANT_ENCODER=ON
 * (libonnxruntime); otherwise rc_encoder_load fails with a clear message and
 * a config that asks for an encoder is rejected at startup. */
#define RC_ENCODER_MAX_TOKENS 512u
typedef struct rc_wordpiece rc_wordpiece;
rc_wordpiece *rc_wordpiece_load(const char *vocab_path);
void rc_wordpiece_free(rc_wordpiece *wp);
/* Token ids for text (UTF-8, length bytes) with [CLS]/[SEP], truncated like
 * the reference tokenizer to max_ids (>= 2). Returns the count, 0 on error. */
size_t rc_wordpiece_encode(const rc_wordpiece *wp, const char *text, size_t length, int64_t *ids, size_t max_ids);

typedef struct rc_encoder rc_encoder;
/* NULL on failure, with a message in err. threads: intra-op threads (1-16). */
rc_encoder *rc_encoder_load(const char *model_path, const char *vocab_path, int threads, char *err, size_t err_len);
void rc_encoder_free(rc_encoder *enc);
size_t rc_encoder_dim(const rc_encoder *enc);
/* Writes rc_encoder_dim() floats (unit length). Thread-safe. false on error. */
bool rc_encoder_embed(rc_encoder *enc, const char *text, size_t length, float *out);
#endif
