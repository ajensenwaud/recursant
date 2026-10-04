#ifndef RECURSANT_CLI_H
#define RECURSANT_CLI_H
#include <limits.h>
#include <stdbool.h>
#include <stddef.h>

/* Where one installation lives. System: /etc/recursant + the system manager;
 * user: ~/.config/recursant + `systemctl --user`. Secrets are kept out of the
 * config, in recursant.env next to it (0600), read by systemd's
 * EnvironmentFile= and by the CLI. */
typedef struct {
    bool user;
    char config[PATH_MAX];
    char env_file[PATH_MAX];
    char unit[PATH_MAX];
    char bin[PATH_MAX]; /* where install copies the binary */
} rc_cli_paths;

int rc_cli_main(int argc, char **argv);
int rc_cli_configure(int argc, char **argv, rc_cli_paths *paths);
int rc_serve_main(const char *config, bool test_mode); /* http/router.c */

void rc_cli_paths_for(bool user, rc_cli_paths *paths);
void rc_cli_env_path(const char *config, char *out, size_t size);
/* NAME=VALUE lines into the environment without overriding variables that are
 * already set. 0 = absent, -1 = refused (readable by group/others, wrong
 * owner) or unreadable, else the number of variables read. */
int rc_cli_load_env(const char *path, bool quiet);
/* Add or replace NAME=VALUE in the env file (0600, atomic). */
bool rc_cli_store_env(const char *path, const char *name, const char *value, char *err, size_t size);
/* Copy path to path.YYYY-MM-DD-HHMMSS.bak (same mode). true when absent. */
bool rc_cli_backup(const char *path, char *backup, size_t size);
/* Atomic write (temporary file + rename), creating parent directories. */
bool rc_cli_write_file(const char *path, const char *data, size_t length, unsigned mode, char *err, size_t size);
/* Full load + compliance policy. secrets=false checks structure only and
 * lists unset key variables; verbose prints a summary to stdout. */
bool rc_cli_check(const char *config, bool secrets, bool verbose, bool test_mode, char *err, size_t size);
#endif
