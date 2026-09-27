#include "recursant/response_observer.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *first="data: {\"choices\":[{\"index\":0,\"delta\":{\"role\":\"assistant\",\"content\":\"café 🦀\"},\"finish_reason\":null}]}\n\n";
static const char *last="data: {\"choices\":[{\"index\":0,\"delta\":{},\"finish_reason\":\"stop\"}]}\n\ndata: [DONE]\n\n";
static void feed(rc_response_observer *o,const char *s){rc_response_observer_feed(o,s,strlen(s));}
static void reject_metadata(void) {
    const char *bad[]={"\"id\":{}", "\"model\":{}", "\"object\":\"response\"", "\"created\":true",
        "\"usage\":{\"prompt_tokens\":1,\"completion_tokens\":1,\"total_tokens\":2,\"prompt_tokens_details\":{\"opaque\":0}}",
        "\"usage\":{\"prompt_tokens\":1,\"completion_tokens\":1,\"total_tokens\":2,\"completion_tokens_details\":{\"reasoning_tokens\":true}}",
        "\"usage\":{\"prompt_tokens\":-1,\"completion_tokens\":1,\"total_tokens\":2}",
        "\"id\":\"first\",\"id\":\"duplicate\""};
    for(size_t i=0;i<sizeof bad/sizeof *bad;i++){
        rc_response_observer *o=calloc(1,sizeof *o);assert(o);
        char data[512];snprintf(data,sizeof data,"data: {%s,\"choices\":[{\"index\":0,\"delta\":{\"role\":\"assistant\",\"content\":\"text\"},\"finish_reason\":null}]}\n\n",bad[i]);
        feed(o,data);feed(o,last);
        json_t *m=rc_response_observer_message(o);
        if(m)fprintf(stderr,"accepted malformed/opaque metadata: %s\n",bad[i]);
        assert(!m);free(o);
    }
}
static void every_split(void) {
    char wire[1024];snprintf(wire,sizeof wire,"%s%s",first,last);
    for(size_t split=0;split<=strlen(wire);split++){
        rc_response_observer *o=calloc(1,sizeof *o);assert(o);
        rc_response_observer_feed(o,wire,split);rc_response_observer_feed(o,wire+split,strlen(wire)-split);
        json_t *m=rc_response_observer_message(o);assert(m);
        assert(!strcmp(json_string_value(json_object_get(m,"content")),"café 🦀"));json_decref(m);free(o);
    }
    rc_response_observer *o=calloc(1,sizeof *o);assert(o);
    for(size_t i=0;i<strlen(wire);i++){
        rc_response_observer_feed(o,wire+i,1);
        if(i+1<strlen(wire))assert(!rc_response_observer_message(o));
    }
    json_t *m=rc_response_observer_message(o);assert(m);json_decref(m);free(o);
}
static void mixed_identity(void) {
    const char *names[]={"id","model","created"};
    for(size_t i=0;i<3;i++){
        rc_response_observer *o=calloc(1,sizeof *o);assert(o);
        char data[512];
        snprintf(data,sizeof data,"data: {\"%s\":%s,\"choices\":[{\"index\":0,\"delta\":{\"role\":\"assistant\"},\"finish_reason\":null}]}\n\n",names[i],i==2?"1":"\"one\"");feed(o,data);
        snprintf(data,sizeof data,"data: {\"%s\":%s,\"choices\":[{\"index\":0,\"delta\":{},\"finish_reason\":\"stop\"}]}\n\ndata: [DONE]\n\n",names[i],i==2?"2":"\"two\"");feed(o,data);
        json_t *m=rc_response_observer_message(o);
        if(m)fprintf(stderr,"accepted mixed generation %s\n",names[i]);
        assert(!m);free(o);
    }
}
static void framing_and_bounds(void) {
    const char *wire=": keepalive\r\ndata: {\"choices\":\r\ndata: [{\"index\":0,\"delta\":{\"role\":\"assistant\",\"content\":\"café 🦀\"},\"finish_reason\":\"stop\"}]}\r\n\r\ndata: [DONE]\r\n\r\n";
    rc_response_observer *o=calloc(1,sizeof *o);assert(o);
    for(size_t i=0;i<strlen(wire);i++)rc_response_observer_feed(o,wire+i,1);
    json_t *m=rc_response_observer_message(o);assert(m);
    assert(!strcmp(json_string_value(json_object_get(m,"content")),"café 🦀"));json_decref(m);
    memset(o,0,sizeof *o);
    char *full=malloc(RC_RESPONSE_LIMIT);assert(full);
    size_t pad=RC_RESPONSE_LIMIT-strlen(first)-strlen(last);
    memset(full,'x',pad);full[0]=':';full[pad-2]='\n';full[pad-1]='\n';
    memcpy(full+pad,first,strlen(first));memcpy(full+pad+strlen(first),last,strlen(last));
    rc_response_observer_feed(o,full,RC_RESPONSE_LIMIT);
    m=rc_response_observer_message(o);assert(m);json_decref(m);
    feed(o,"\n");assert(!rc_response_observer_message(o));feed(o,first);feed(o,last);assert(!rc_response_observer_message(o));
    free(full);free(o);
}
static void invalid_comment_utf8(void) {
    rc_response_observer *o=calloc(1,sizeof *o);assert(o);
    feed(o,": invalid \xff\n\n");feed(o,first);feed(o,last);
    assert(!rc_response_observer_message(o));free(o);
}
int main(void){every_split();reject_metadata();mixed_identity();framing_and_bounds();invalid_comment_utf8();puts("response observer tests passed");return 0;}
