#include <jansson.h>
#include <stdio.h>
#include <unistd.h>
#include <string.h>
json_t *__real_json_deep_copy(const json_t *);
char *__real_json_dumps(const json_t *,size_t);
static int armed(void){FILE *f=fopen("/tmp/rc-tool-oom-target","r");if(!f)return 0;int c=fgetc(f);fclose(f);return c;}
static int role(const json_t *o,const char *s){const char *v=json_string_value(json_object_get(o,"role"));return v&&!strcmp(v,s);}
json_t *__wrap_json_deep_copy(const json_t *o){
 int c=armed();json_t *first=json_array_get(o,0);
 int hit=(c=='h'&&role(first,"user"))||(c=='t'&&json_object_get(first,"function")&&!json_object_get(first,"id"))||(c=='c'&&json_is_object(o)&&json_object_get(o,"function"))||(c=='o'&&json_object_get(first,"id"));
 if(hit){unlink("/tmp/rc-tool-oom-target");return NULL;}return __real_json_deep_copy(o);
}
char *__wrap_json_dumps(const json_t *o,size_t flags){
 if(armed()=='r'&&json_array_size(o)&&role(json_array_get(o,json_array_size(o)-1),"tool")){unlink("/tmp/rc-tool-oom-target");return NULL;}return __real_json_dumps(o,flags);
}
