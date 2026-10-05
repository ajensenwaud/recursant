#include "recursant/response_observer.h"
#include <string.h>
#include <stdio.h>
#include <math.h>
#include <stdlib.h>
#include "recursant/stream_tools.h"

static bool keys(json_t *o, const char *ordinary, const char *nullable) {
    if(!json_is_object(o))return false;
    const char *k;json_t *v;
    json_object_foreach(o,k,v){
        char b[128];
        if(!*k||strchr(k,'|')||snprintf(b,sizeof b,"|%s|",k)>=(int)sizeof b)return false;
        if(!strstr(ordinary,b)&&(!strstr(nullable,b)||!json_is_null(v)))return false;
    }
    return true;
}
static bool string_is(json_t *v,const char *s) {
    return json_is_string(v)&&json_string_length(v)==strlen(s)&&!strcmp(json_string_value(v),s);
}
static bool counts(json_t *v,const char *allowed) {
    if(!keys(v,allowed,""))return false;
    const char *k;json_t *n;
    json_object_foreach(v,k,n){(void)k;if(!json_is_integer(n)||json_integer_value(n)<0)return false;}
    return true;
}
static bool cost(json_t *v) {
    return json_is_number(v)&&isfinite(json_number_value(v))&&json_number_value(v)>=0;
}
static bool costs(json_t *v) {
    if(!keys(v,"|upstream_inference_cost||upstream_inference_prompt_cost||upstream_inference_completions_cost|",""))return false;
    const char *k;json_t *n;
    json_object_foreach(v,k,n){(void)k;if(!cost(n))return false;}
    return true;
}
/* strict: OpenAI usage shape only; OpenRouter cost/BYOK/extra counters are
 * unknown (unportable) fields for openai-compatible adapters. */
static bool usage(json_t *v,bool strict) {
    if(!keys(v,strict?"|prompt_tokens||completion_tokens||total_tokens||prompt_tokens_details||completion_tokens_details|":
             "|prompt_tokens||completion_tokens||total_tokens||prompt_tokens_details||completion_tokens_details||cost||is_byok||cost_details|",""))return false;
    const char *required[]={"prompt_tokens","completion_tokens","total_tokens"};
    for(size_t i=0;i<3;i++){
        json_t *n=json_object_get(v,required[i]);
        if(!json_is_integer(n)||json_integer_value(n)<0)return false;
    }
    json_t *prompt=json_object_get(v,"prompt_tokens_details"),*completion=json_object_get(v,"completion_tokens_details");
    json_t *amount=json_object_get(v,"cost"),*byok=json_object_get(v,"is_byok"),*details=json_object_get(v,"cost_details");
    return (!amount||cost(amount))&&(!byok||json_is_boolean(byok))&&(!details||costs(details))&&
        (!prompt||json_is_null(prompt)||counts(prompt,strict?"|cached_tokens||audio_tokens|":"|cached_tokens||cache_write_tokens||audio_tokens||video_tokens|"))&&
        (!completion||json_is_null(completion)||counts(completion,strict?"|reasoning_tokens||audio_tokens||accepted_prediction_tokens||rejected_prediction_tokens|":
                                                        "|reasoning_tokens||image_tokens||audio_tokens||accepted_prediction_tokens||rejected_prediction_tokens|"));
}
static bool identity(char stored[129],json_t *v) {
    if(!v)return true;
    if(!json_is_string(v)||!json_string_length(v)||json_string_length(v)>128)return false;
    const char *s=json_string_value(v);
    if(strlen(s)!=json_string_length(v)||(stored[0]&&strcmp(stored,s)))return false;
    strcpy(stored,s);return true;
}
/* One OpenRouter reasoning_details element: a known type with its string
 * payload; id null|string, format string, index integer, signature null|string. */
static const char *reasoning_payload(json_t *e) {
    const char *type=json_string_value(json_object_get(e,"type"));
    const char *field=!type?NULL:!strcmp(type,"reasoning.text")?"text":!strcmp(type,"reasoning.summary")?"summary":
        !strcmp(type,"reasoning.encrypted")?"data":NULL;
    json_t *id=json_object_get(e,"id"),*format=json_object_get(e,"format"),*index=json_object_get(e,"index"),*sig=json_object_get(e,"signature");
    json_t *payload=field?json_object_get(e,field):NULL;
    /* Claude (OpenRouter) closes its reasoning with a signature-only text delta. */
    bool signature_only=field&&!strcmp(field,"text")&&!payload&&json_is_string(sig);
    if(!field||!keys(e,"|type||text||summary||data||id||format||index||signature|","")||
       (!signature_only&&(!json_is_string(payload)||json_string_length(payload)!=strlen(json_string_value(payload))))||
       (strcmp(field,"text")&&json_object_get(e,"text"))||(strcmp(field,"summary")&&json_object_get(e,"summary"))||
       (strcmp(field,"data")&&json_object_get(e,"data"))||
       (id&&!json_is_null(id)&&!json_is_string(id))||(format&&!json_is_string(format))||
       (index&&!json_is_integer(index))||(sig&&!json_is_null(sig)&&!json_is_string(sig)))return NULL;
    return field;
}
static bool truthy_string(json_t *v){return json_is_string(v)&&json_string_length(v);}
/* JS `target.k ||= source.k` (k holds null|string): a falsy target takes the
 * source value; a missing source value leaves the key undefined (dropped). */
static bool falsy_fill(json_t *t,json_t *s,const char *k) {
    if(truthy_string(json_object_get(t,k)))return true;
    json_t *sv=json_object_get(s,k);
    return sv?!json_object_set(t,k,sv):(!json_object_get(t,k)||!json_object_del(t,k));
}
/* JS `target.k ??= source.k`: a missing or null target takes the source value;
 * a missing source value leaves the key undefined (dropped by JSON). */
static bool nullish_fill(json_t *t,json_t *s,const char *k) {
    json_t *tv=json_object_get(t,k);
    if(tv&&!json_is_null(tv))return true;
    json_t *sv=json_object_get(s,k);
    return sv?!json_object_set(t,k,sv):(!tv||!json_object_del(t,k));
}
static void reasoning_add(rc_response_observer *o,json_t *e) {
    const char *field=reasoning_payload(e);
    if(!field){o->reasoning_failed=true;return;}
    size_t n=json_string_length(json_object_get(e,field));
    if(n>RC_REASONING_MAX_BYTES-o->reasoning_bytes){o->reasoning_failed=true;return;}
    if(!o->reasoning&&!(o->reasoning=json_array())){o->reasoning_failed=true;return;}
    json_t *last=json_array_get(o->reasoning,json_array_size(o->reasoning)-1);
    const char *type=json_string_value(json_object_get(e,"type"));
    bool mergeable=strcmp(field,"data")&&last&&!strcmp(json_string_value(json_object_get(last,"type")),type);
    if(mergeable){
        /* Consecutive text/summary: append; signature ||=, id ??=, format ||=, index ??=. */
        json_t *prev=json_object_get(last,field),*more=json_object_get(e,field);
        size_t m=json_string_length(prev);
        char *joined=malloc(m+n+1);
        if(!joined){o->reasoning_failed=true;return;}
        if(m)memcpy(joined,json_string_value(prev),m);
        if(n)memcpy(joined+m,json_string_value(more),n);
        bool ok=(!prev&&!more)||!json_object_set_new(last,field,json_stringn(joined,m+n));free(joined);
        if(ok&&!strcmp(field,"text"))ok=falsy_fill(last,e,"signature");
        ok=ok&&nullish_fill(last,e,"id")&&falsy_fill(last,e,"format")&&nullish_fill(last,e,"index");
        if(!ok){o->reasoning_failed=true;return;}
    }else{
        json_t *copy=json_array_size(o->reasoning)<RC_REASONING_MAX_ELEMENTS?json_deep_copy(e):NULL;
        if(!copy||json_array_append_new(o->reasoning,copy)){o->reasoning_failed=true;return;}
    }
    o->reasoning_bytes+=n;
}
static bool chunk(rc_response_observer *o,json_t *root) {
    const bool strict=o->strict_openai;
    if(!keys(root,strict?"|id||object||created||model||choices||usage||system_fingerprint||service_tier|":
             "|id||object||created||model||provider||choices||usage||system_fingerprint||service_tier|",
             "|prompt_logprobs||prompt_token_ids||prompt_text||kv_transfer_params||ec_transfer_params||metrics|"))return false;
    json_t *tier=json_object_get(root,"service_tier");
    if(tier&&!json_is_null(tier)&&!string_is(tier,"default"))return false;
    json_t *id=json_object_get(root,"id"),*model=json_object_get(root,"model");
    json_t *object=json_object_get(root,"object"),*created=json_object_get(root,"created");
    if(!identity(o->id,id)||!identity(o->model,model)||!identity(o->provider,json_object_get(root,"provider"))||
       (object&&!string_is(object,"chat.completion.chunk"))||
       (created&&(!json_is_integer(created)||json_integer_value(created)<0)))return false;
    if(created){
        if(o->has_created&&o->created!=json_integer_value(created))return false;
        o->created=json_integer_value(created);o->has_created=true;
    }
    json_t *fingerprint=json_object_get(root,"system_fingerprint");
    if(fingerprint&&!json_is_string(fingerprint))return false;
    json_t *choices=json_object_get(root,"choices"),*c=json_array_get(choices,0);
    json_t *u=json_object_get(root,"usage");
    if(u&&!json_is_null(u)&&!usage(u,strict))return false;
    if(u&&!json_is_null(u)){
        /* Record the validated counts; a second differing usage is not ours
         * to reconcile, so it fails closed as cost evidence only. */
        json_t *d=json_object_get(u,"prompt_tokens_details"),*k=json_is_object(d)?json_object_get(d,"cached_tokens"):NULL;
        json_int_t pt=json_integer_value(json_object_get(u,"prompt_tokens")),ct=json_integer_value(json_object_get(u,"completion_tokens"));
        json_int_t ca=k?json_integer_value(k):0;
        if(ca>pt)return false;
        if(o->usage_known&&(o->usage_prompt!=pt||o->usage_completion!=ct||o->usage_cached!=ca))return false;
        o->usage_known=true;o->usage_prompt=pt;o->usage_completion=ct;o->usage_cached=ca;
    }
    /* One empty-choices usage tail after finish: OpenAI include_usage shape. */
    if(json_is_array(choices)&&!json_array_size(choices)){
        if(!o->finished||o->accounting_tail||!usage(u,strict))return false;
        o->accounting_tail=true;return true;
    }
    if(!json_is_array(choices)||json_array_size(choices)!=1)return false;
    if(!keys(c,strict?"|index||delta||finish_reason||stop_reason|":"|index||delta||finish_reason||native_finish_reason||stop_reason|",
             "|logprobs||token_ids||routed_experts|"))return false;
    json_t *index=json_object_get(c,"index"),*stop=json_object_get(c,"stop_reason");
    if(!json_is_integer(index)||json_integer_value(index)!=0||
       (stop&&(!json_is_integer(stop)||json_integer_value(stop)<0)))return false;
    json_t *delta=json_object_get(c,"delta"),*finish=json_object_get(c,"finish_reason");
    json_t *native=json_object_get(c,"native_finish_reason");
    /* Match terminal native metadata to its exact supported finish mode.
     * Live OpenRouter openai/gpt-4.1 (pilot-1) reports "completed" for a
     * tool_calls finish; the finish/tail consistency check below still binds. */
    /* Anthropic models on OpenRouter report Anthropic's own stop reasons:
     * "tool_use" for a tool_calls finish, "end_turn" for a stop finish. */
    if(native&&!json_is_null(native)&&
       !((string_is(native,"completed")&&(string_is(finish,"stop")||string_is(finish,"tool_calls")))||
         (string_is(native,"tool_calls")&&string_is(finish,"tool_calls"))||
         (string_is(native,"tool_use")&&string_is(finish,"tool_calls"))||
         (string_is(native,"end_turn")&&string_is(finish,"stop"))))return false;
    if(!keys(delta,o->drop_reasoning?"|role||content||tool_calls||reasoning||reasoning_content||reasoning_details|":"|role||content||tool_calls|",
             "|refusal||annotations||audio||function_call|"))return false;
    /* Opt-in (context.reasoning_text "drop"): readable reasoning text (vLLM
     * "reasoning", "reasoning_content") and OpenRouter's reasoning_details
     * array (Claude's signed or redacted thinking blocks) are left out of the
     * replayable message. Whether a harness replays them is checked by the
     * exact replay of the next request: a harness that sends thinking back
     * makes the next request differ, which pins as before. Any other shape
     * (an object where text is expected) fails closed. */
    json_t *thinking[]={json_object_get(delta,"reasoning"),json_object_get(delta,"reasoning_content")};
    for(size_t k=0;k<2;k++)if(thinking[k]&&!json_is_null(thinking[k])&&!json_is_string(thinking[k]))return false;
    json_t *details=json_object_get(delta,"reasoning_details");
    if(details&&!json_is_null(details)&&!json_is_array(details))return false;
    if(json_array_size(details)){
        /* Reasoning after the finish is not part of this completion's record. */
        if(o->finished)o->reasoning_failed=true;
        size_t i;json_t *e;
        json_array_foreach(details,i,e)if(!o->reasoning_failed)reasoning_add(o,e);
    }
    json_t *role=json_object_get(delta,"role"),*text=json_object_get(delta,"content");
    /* OpenRouter repeats the empty terminal choice with accounting. This is
     * not a second completion or permission to append state after finish. */
    if(o->finished){
        if(strict||o->accounting_tail||!usage(u,strict)||!string_is(finish,o->tool_finish?"tool_calls":"stop")||
           json_object_get(delta,"tool_calls")||
           (text&&!string_is(text,""))||
           o->native_completed!=string_is(native,"completed")||
           o->native_tool_calls!=string_is(native,"tool_calls")||
           o->native_tool_use!=string_is(native,"tool_use")||
           o->native_end_turn!=string_is(native,"end_turn"))return false;
        o->accounting_tail=true;
    }
    if(role){if(!string_is(role,"assistant"))return false;o->role=true;}
    if(!o->role)return false;
    if(text&&!json_is_null(text)){
        if(!json_is_string(text))return false;
        size_t n=json_string_length(text);
        if(n!=strlen(json_string_value(text))||n>RC_RESPONSE_LIMIT-o->text_used)return false;
        memcpy(o->text+o->text_used,json_string_value(text),n);o->text_used+=n;
    }
    json_t *calls=json_object_get(delta,"tool_calls");
    if(calls){
        if(!json_is_array(calls))return false;
        if(json_array_size(calls)){
            if(!o->tools&&!o->tools_failed&&!(o->tools=rc_stream_tools_new()))o->tools_failed=true;
            if(!o->tools_failed&&!rc_stream_tools_feed(o->tools,calls))o->tools_failed=true;
            o->tool_used++;
        }
    }
    if(!finish)return false;
    if(!json_is_null(finish)){
        bool tools=string_is(finish,"tool_calls");
        if(!tools&&!string_is(finish,"stop"))return false;
        if(tools!=(o->tool_used!=0))return false;
        o->tool_finish=tools;
        o->native_completed=string_is(native,"completed");
        o->native_tool_calls=string_is(native,"tool_calls");
        o->native_tool_use=string_is(native,"tool_use");
        o->native_end_turn=string_is(native,"end_turn");
        o->finished=true;
    }
    return true;
}
static void event(rc_response_observer *o) {
    if(!o->event_used)return;
    /* Each data line contributes a final newline; SSE removes the last one. */
    size_t n=o->event_used-1;
    if(o->done)o->failed=true;
    else if(n==6&&!memcmp(o->event,"[DONE]",6)){
        if(!o->finished)o->failed=true;
        else o->done=true;
    }else{
        json_error_t error;
        json_t *root=json_loadb(o->event,n,JSON_REJECT_DUPLICATES,&error);
        if(!chunk(o,root))o->failed=true;
        json_decref(root);
    }
    o->event_used=0;
}
static void line(rc_response_observer *o) {
    size_t n=o->line_used;
    if(!n)event(o);
    else if(o->line[0]==':'){
        /* Ignored SSE keepalives still must be valid UTF-8. */
        json_t *comment=json_stringn(o->line,n);
        if(!comment)o->failed=true;
        json_decref(comment);
    }
    else if(n>=5&&!memcmp(o->line,"data:",5)){
        size_t start=5;if(n>start&&o->line[start]==' ')start++;
        size_t bytes=n-start;
        if(bytes+1>RC_RESPONSE_LIMIT-o->event_used)o->failed=true;
        else{
            memcpy(o->event+o->event_used,o->line+start,bytes);o->event_used+=bytes;
            o->event[o->event_used++]='\n';
        }
    }else o->failed=true; /* Unknown SSE fields are not portable state. */
    o->line_used=0;
}
void rc_response_observer_feed(rc_response_observer *o,const char *data,size_t n) {
    if(o->failed)return;
    if(n>RC_RESPONSE_WIRE_LIMIT-o->total){o->failed=true;return;}
    o->total+=n;
    for(size_t i=0;i<n&&!o->failed;i++){
        unsigned char c=(unsigned char)data[i];
        if(!c){o->failed=true;break;}
        if(o->cr){o->cr=false;if(c=='\n')continue;}
        if(c=='\r'||c=='\n'){line(o);o->cr=c=='\r';}
        else if(o->line_used==RC_RESPONSE_LIMIT){o->failed=true;break;} /* per-line bound, independent of wire bound */
        else o->line[o->line_used++]=(char)c;
    }
}
json_t *rc_response_observer_message(const rc_response_observer *o) {
    if(!o||o->failed||!o->done||!o->finished||!o->role||o->line_used||o->event_used)return NULL;
    json_t *m=json_pack("{s:s,s:s#}","role","assistant","content",o->text,(int)o->text_used);
    if(!m||!o->tool_finish)return m;
    bool valid=o->tools&&!o->tools_failed;
    json_t *calls=valid?rc_stream_tools_snapshot(o->tools):NULL;
    if(!calls||json_object_set_new(m,"tool_calls",calls)){
        json_decref(m);return NULL;
    }
    /* Pinned Hermes storage flattens stream None to "" before replay.
     * Do not equate a caller's null/missing content with this exact snapshot. */
    char *encoded=json_dumps(m,JSON_COMPACT);
    valid=encoded&&strlen(encoded)<=RC_STREAM_TOOLS_MAX_BYTES;
    free(encoded);
    if(!valid){json_decref(m);return NULL;}
    return m;
}
json_t *rc_response_observer_reasoning(const rc_response_observer *o) {
    if(!o||o->failed||!o->done||!o->finished||!o->role||o->line_used||o->event_used||
       o->reasoning_failed||!json_array_size(o->reasoning))return NULL;
    return json_incref(o->reasoning);
}
void rc_response_observer_release(rc_response_observer *o) {
    if(!o)return;
    rc_stream_tools_free(o->tools);o->tools=NULL;
    json_decref(o->reasoning);o->reasoning=NULL;
}
