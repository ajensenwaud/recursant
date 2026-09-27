#define _POSIX_C_SOURCE 200809L
#include "recursant/interpreter.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <curl/curl.h>
#include <time.h>
#include <stdlib.h>
#include <dirent.h>
static size_t entries(const char *path) {
 DIR *d=opendir(path); assert(d); size_t n=0;
 while(readdir(d)) n++;
 closedir(d); return n;
}
static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return t.tv_sec+t.tv_nsec/1e9; }
int main(int argc, char **argv) {
 if(argc>1) {
  assert(curl_global_init(CURL_GLOBAL_DEFAULT)==0);
  rc_interpreter_config cfg={.enabled=false,.url=argv[1],.model="fixture",.max_tokens=4096,.deadline_ms=1000};
  size_t tasks=entries("/proc/self/task"), fds=entries("/proc/self/fd");
  assert(!rc_interpreter_create(&cfg));
  assert(entries("/proc/self/task")==tasks && entries("/proc/self/fd")==fds);
  cfg.enabled=true;
  cfg.max_tokens=4097; assert(!rc_interpreter_create(&cfg)); cfg.max_tokens=4096;
  cfg.deadline_ms=2001; assert(!rc_interpreter_create(&cfg)); cfg.deadline_ms=1000;
  cfg.url="file:///etc/passwd"; assert(!rc_interpreter_create(&cfg));
  cfg.url="http://user:pass@127.0.0.1/"; assert(!rc_interpreter_create(&cfg));
  cfg.url=argv[1];
  rc_interpreter *w=rc_interpreter_create(&cfg); assert(w);
  rc_interpreter_input job={.revision=1,.evidence_count=1};
  strcpy(job.key.tenant,"t"); strcpy(job.key.project,"p"); strcpy(job.key.task_generation,"g");
  strcpy(job.key.branch,"b"); strcpy(job.key.step,"s"); strcpy(job.key.attempt,"a");
  strcpy(job.evidence[0].id,"e1"); strcpy(job.evidence[0].source,"executor"); strcpy(job.evidence[0].text,"test failed");
  double start=now();
  for(int i=0;i<4;i++) {
   while(!rc_interpreter_try_submit(w,&job)) assert(now()-start<0.2);
  }
  assert(!rc_interpreter_try_submit(w,&job));
  rc_context_registry *reg=rc_context_create(1,100);
  assert(rc_context_put(reg,&job.key,1,1,100,"e1",false)==RC_CONTEXT_OK);
  rc_context_snapshot snap;
  for(int i=0;i<1000;i++) assert(rc_context_get(reg,&job.key,1,&snap)==RC_CONTEXT_OK);
  assert(now()-start<0.2);
  strcpy(job.evidence[0].text,"mutated");
  struct timespec active_pause={0,50000000}; nanosleep(&active_pause,NULL);
  if(argc>2 && !strcmp(argv[2],"cancel")) rc_interpreter_cancel(w);
  if(argc>2 && !strcmp(argv[2],"0")) {
   struct timespec completion_pause={0,700000000}; nanosleep(&completion_pause,NULL);
   assert(!rc_interpreter_try_submit(w,&job)); /* completions retain capacity */
  }
  if(argc>2 && !strcmp(argv[2],"shutdown")) {
   start=now(); rc_interpreter_destroy(w); assert(now()-start<0.5);
  } else {
   rc_interpreter_result result; int n=0;
   while(n<4 && now()-start<4) {
    if(rc_interpreter_poll(w,&result)) {
     rc_interpreter_status expected=argc>2 && !strcmp(argv[2],"cancel") ? RC_INTERPRETER_CANCELLED :
        (rc_interpreter_status)atoi(argc>2?argv[2]:"0");
     assert(result.status==expected);
     assert(result.revision==1 && !strcmp(result.key.tenant,"t")); n++;
     if(result.status==RC_INTERPRETER_VALID) {
      if(n==1) assert(rc_context_interpret(reg,&result.key,result.revision,1,result.phase)==RC_CONTEXT_OK);
      assert(rc_context_put(reg,&result.key,2,2,100,"new",false)==(n==1?RC_CONTEXT_OK:RC_CONTEXT_CONFLICT));
      assert(rc_context_interpret(reg,&result.key,result.revision,2,result.phase)==RC_CONTEXT_CONFLICT);
     }
    }
    struct timespec pause={0,1000000}; nanosleep(&pause,NULL);
   }
   assert(n==4);
   if(argc>2 && !strcmp(argv[2],"cancel")) assert(now()-start<0.5);
   rc_interpreter_destroy(w);
  }
  rc_context_destroy(reg); curl_global_cleanup(); return 0;
 }
 rc_interpreter_input in = {.revision=1,.evidence_count=1};
 strcpy(in.evidence[0].id,"e1");
 rc_interpreter_result out;
 char buf[65537]; size_t n=fread(buf,1,sizeof(buf),stdin);
 bool ok=rc_interpreter_validate(buf,n,&in,&out);
 if(ok) puts(out.phase);
 return ok?0:1;
}
