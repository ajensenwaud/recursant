#include "recursant/tool_boundary.h"
#include <jansson.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
static size_t alloc_calls, fail_after=SIZE_MAX;
static int deny_calloc;
void *__real_calloc(size_t, size_t);
void *__wrap_calloc(size_t a,size_t b) { return deny_calloc ? NULL : __real_calloc(a,b); }
static void *fault_malloc(size_t n) { size_t i=alloc_calls++; return i>=fail_after ? NULL : malloc(n); }
static const char *s(json_t *j,const char *key) { const char *v=json_string_value(json_object_get(j,key)); assert(v);return v; }
static rc_tool_status status(const char *s) {
 if (!strcmp(s,"COMPLETE")) return RC_TOOL_COMPLETE;
 if (!strcmp(s,"INCOMPLETE")) return RC_TOOL_INCOMPLETE;
 if (!strcmp(s,"LIMIT")) return RC_TOOL_LIMIT;
 assert(!strcmp(s,"INVALID")); return RC_TOOL_INVALID;
}
static void check_status(rc_tool_status got,rc_tool_status want,const char *name) {
 if (got!=want) { fprintf(stderr,"FAIL %s: got=%d expected=%d\n",name,got,want);abort(); }
}
static char *owned(const char *s) { char *v=malloc(strlen(s)+1); assert(v);strcpy(v,s);return v; }
int main(int argc,char **argv) {
 assert(argc==2); json_error_t e;json_t *cases=json_load_file(argv[1],0,&e);assert(json_is_array(cases));
 size_t count=json_array_size(cases);
 for(size_t i=0;i<count;i++) {
  json_t *c=json_array_get(cases,i);const char *name=s(c,"name"),*h=s(c,"history"),*a=s(c,"assistant"),*r=s(c,"replay");
  char *hc=owned(h),*ac=owned(a);rc_tool_boundary *b=(rc_tool_boundary *)(uintptr_t)1;
  rc_tool_status got=rc_tool_boundary_capture(hc,strlen(hc),ac,strlen(ac),&b);
  check_status(got,status(s(c,"capture")),name);
  memset(hc,'x',strlen(hc));memset(ac,'x',strlen(ac));free(hc);free(ac);
  if(got!=RC_TOOL_COMPLETE) { assert(!b);continue; }
  uint32_t req=(uint32_t)json_integer_value(json_object_get(c,"requirements")); assert(rc_tool_boundary_requirements(b)==req);
  for(uint32_t known=0;known<16;known++) for(uint32_t supported=0;supported<16;supported++)
   assert(rc_tool_boundary_candidate(b,known,supported)==(((known&req)==req)&&((supported&req)==req)));
  check_status(rc_tool_boundary_replay(b,r,strlen(r)),status(s(c,"status")),name);
  // No persistent state: invalid replay must not corrupt snapshot, but caller owns pins.
  assert(rc_tool_boundary_replay(b,"[]",2)==RC_TOOL_INVALID);
  check_status(rc_tool_boundary_replay(b,r,strlen(r)),status(s(c,"status")),name);
  assert(rc_tool_boundary_candidate(b,req,req));
  rc_tool_boundary_free(b);
 }
 printf("adversarial corpus: %zu cases PASS; ownership, lifecycle, capability matrix PASS\n",count);
 json_t *c=json_array_get(cases,13); // select a complete case below instead of depending on index
 for(size_t i=0;i<count;i++) {json_t *v=json_array_get(cases,i);if(!strcmp(s(v,"capture"),"COMPLETE")&&!strcmp(s(v,"status"),"COMPLETE")){c=v;break;}}
 const char *h=s(c,"history"),*a=s(c,"assistant"),*r=s(c,"replay");rc_tool_boundary *b=NULL;
 deny_calloc=1; assert(rc_tool_boundary_capture(h,strlen(h),a,strlen(a),&b)==RC_TOOL_NOMEM); assert(!b);deny_calloc=0;
 json_set_alloc_funcs(fault_malloc,free);alloc_calls=0;
 assert(rc_tool_boundary_capture(h,strlen(h),a,strlen(a),&b)==RC_TOOL_COMPLETE);size_t capture_allocs=alloc_calls;rc_tool_boundary_free(b);
 for(size_t i=0;i<capture_allocs;i++) {alloc_calls=0;fail_after=i;b=(rc_tool_boundary *)(uintptr_t)1;
  rc_tool_status got=rc_tool_boundary_capture(h,strlen(h),a,strlen(a),&b);assert(got!=RC_TOOL_COMPLETE);assert(!b);fail_after=SIZE_MAX;}
 assert(rc_tool_boundary_capture(h,strlen(h),a,strlen(a),&b)==RC_TOOL_COMPLETE);
 alloc_calls=0;assert(rc_tool_boundary_replay(b,r,strlen(r))==RC_TOOL_COMPLETE);size_t replay_allocs=alloc_calls;
 for(size_t i=0;i<replay_allocs;i++) {alloc_calls=0;fail_after=i;
  assert(rc_tool_boundary_replay(b,r,strlen(r))!=RC_TOOL_COMPLETE);fail_after=SIZE_MAX;
  assert(rc_tool_boundary_replay(b,r,strlen(r))==RC_TOOL_COMPLETE);}
 printf("allocation faults: calloc=1 capture=%zu replay=%zu positions PASS\n",capture_allocs,replay_allocs);
 // Real byte boundaries, including exactly max bytes with whitespace padding.
 char *buf=malloc(RC_TOOL_MAX_BYTES+1);assert(buf);size_t n=strlen(r);assert(n<RC_TOOL_MAX_BYTES);
 memcpy(buf,r,n);memset(buf+n,' ',RC_TOOL_MAX_BYTES+1-n);
 assert(rc_tool_boundary_replay(b,buf,RC_TOOL_MAX_BYTES)==RC_TOOL_COMPLETE);
 assert(rc_tool_boundary_replay(b,buf,RC_TOOL_MAX_BYTES+1)==RC_TOOL_LIMIT);
 rc_tool_boundary_free(b);b=NULL;n=strlen(h);memcpy(buf,h,n);memset(buf+n,' ',RC_TOOL_MAX_BYTES+1-n);
 assert(rc_tool_boundary_capture(buf,RC_TOOL_MAX_BYTES,a,strlen(a),&b)==RC_TOOL_COMPLETE);rc_tool_boundary_free(b);
 assert(rc_tool_boundary_capture(buf,RC_TOOL_MAX_BYTES+1,a,strlen(a),&b)==RC_TOOL_LIMIT);assert(!b);
 n=strlen(a);memcpy(buf,a,n);memset(buf+n,' ',RC_TOOL_MAX_BYTES+1-n);
 assert(rc_tool_boundary_capture(h,strlen(h),buf,RC_TOOL_MAX_BYTES,&b)==RC_TOOL_COMPLETE);rc_tool_boundary_free(b);
 assert(rc_tool_boundary_capture(h,strlen(h),buf,RC_TOOL_MAX_BYTES+1,&b)==RC_TOOL_LIMIT);assert(!b);
 free(buf);json_set_alloc_funcs(malloc,free);json_decref(cases);puts("exact byte bounds PASS");return 0;
}
