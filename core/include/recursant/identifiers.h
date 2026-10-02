#ifndef RECURSANT_IDENTIFIERS_H
#define RECURSANT_IDENTIFIERS_H
#include <stdbool.h>
#include <stddef.h>
/* Personal identifiers the compliance engine can recognise (compliance.identifiers).
 * Check-digit kinds are found by rc_identifiers_scan; the others are format rules with a
 * nearby keyword, compiled as extra patterns (rc_identifier_pattern). Deterministic:
 * a match only ever makes placement stricter (private), like any pattern rule. */
#define RC_ID_TFN       1u   /* Australian tax file number: 9 digits, ATO mod-11 check */
#define RC_ID_MEDICARE  2u   /* Medicare card: 10 or 11 digits, mod-10 check digit */
#define RC_ID_ABN       4u   /* Australian business number: 11 digits, mod-89 check */
#define RC_ID_CARD      8u   /* payment card: Luhn and a real card shape */
#define RC_ID_PHONE     16u  /* Australian mobile or landline */
#define RC_ID_BANK      32u  /* BSB and account */
#define RC_ID_PASSPORT  64u  /* letter + 7 digits after the word passport */
#define RC_ID_LICENCE   128u /* 6 to 10 digits after licence/license */
#define RC_ID_DOB       256u /* a date after DOB / date of birth / born */
#define RC_ID_CHECKED   (RC_ID_TFN|RC_ID_MEDICARE|RC_ID_ABN|RC_ID_CARD)
/* Config name ("au_tfn", "au_medicare", "au_abn", "payment_card", "au_phone",
 * "au_bank_account", "passport", "drivers_licence", "date_of_birth") -> bit. */
bool rc_identifier_name(const char *name, unsigned *bit);
/* Check-digit kinds in mask found in text: one unbroken digit run or the identifier's
 * printed layout (TFN 3-3-3, Medicare 4-5-1, ABN 2-3-3-3, card 4-4-4-4 or 4-6-5, single
 * space or hyphen between groups), with no letter or digit on either side. Returns the
 * kinds found. Bounded, no allocation. */
unsigned rc_identifiers_scan(const char *text, size_t length, unsigned mask);
/* PCRE2 pattern for a format kind, NULL for check-digit kinds. */
const char *rc_identifier_pattern(unsigned bit);
#endif
