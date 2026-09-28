#include "recursant/signals.h"
/* RED stub: S4 classifier not implemented yet. */
uint64_t rc_signals_classify(json_t *body, const rc_signal_scope *scope) { (void)body; (void)scope; return 0; }
bool rc_signals_failed_text(const char *text, size_t length) { (void)text; (void)length; return false; }
bool rc_task_qualifiable(const char *name, uint64_t *bit) { (void)name; (void)bit; return false; }
const char *rc_task_name(uint64_t bit) { (void)bit; return "none"; }
