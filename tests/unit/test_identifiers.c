#include "recursant/identifiers.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __func__, __LINE__, #x); exit(1); } } while (0)
static unsigned scan(const char *t) { return rc_identifiers_scan(t, strlen(t), RC_ID_CHECKED); }
int main(void) {
    /* Published examples: ATO TFN 123 456 782, ABR ABN 51 824 753 556, test Visa. */
    CHECK(scan("TFN 123456782") == RC_ID_TFN);
    CHECK(scan("tfn: 123 456 782.") == RC_ID_TFN);
    CHECK(scan("123-456-782") == RC_ID_TFN);
    CHECK(scan("order 123456789 shipped") == 0);              /* fails the check */
    CHECK(scan("ABN 51 824 753 556") == RC_ID_ABN);
    CHECK(scan("51824753556") == RC_ID_ABN);
    CHECK(scan("card 4111 1111 1111 1111 exp") == RC_ID_CARD);
    CHECK(scan("4111111111111111") == RC_ID_CARD);
    CHECK(scan("ts=4836516046417 done") == 0);                 /* 13 digits: not a card shape */
    CHECK(scan("Medicare 4957 48900 7") == RC_ID_MEDICARE);    /* 4-5-1 as printed on the card */
    CHECK(scan("4957489007") == RC_ID_MEDICARE);
    CHECK(scan("49574890071") == RC_ID_MEDICARE);              /* with the individual reference */
    CHECK(scan("4957489017") == 0);
    /* Digits inside hashes, identifiers and longer runs do not count. */
    CHECK(scan("commit 4f26f8342c5a43213680398b9f962093") == 0);
    CHECK(scan("id a123456782b") == 0);
    CHECK(scan("x123456782") == 0);
    CHECK(scan("1234567821") == 0 || scan("1234567821") == RC_ID_MEDICARE);   /* 10 digits are not a TFN */
    CHECK(!(scan("1234567821") & RC_ID_TFN));
    CHECK(scan("12345678200000000000000") == 0);
    CHECK(scan("1 2 3 4 5 6 7 8 2") == 0);                     /* single digits in a list */
    /* Columns of numbers are not identifiers, even when the digits pass a check
     * (ls -l: "1000 124 4096" would be ABN-valid if joined). */
    CHECK(scan("drwx------ 2 1000 124 4096 Oct  1 04:38 .") == 0);
    CHECK(scan("12 34 567 82") == 0);                          /* TFN digits, wrong layout */
    CHECK(scan("3782 822463 10005") == RC_ID_CARD);            /* Amex 4-6-5 */
    /* Mask limits what is reported. */
    CHECK(rc_identifiers_scan("123456782", 9, RC_ID_ABN) == 0);
    CHECK(rc_identifiers_scan("123456782 51824753556", 21, RC_ID_TFN | RC_ID_ABN) == (RC_ID_TFN | RC_ID_ABN));
    /* Bounds: a length shorter than the text is honoured. */
    CHECK(rc_identifiers_scan("123456782", 8, RC_ID_TFN) == 0);
    /* Names. */
    unsigned bit = 0;
    CHECK(rc_identifier_name("au_tfn", &bit) && bit == RC_ID_TFN);
    CHECK(rc_identifier_name("date_of_birth", &bit) && bit == RC_ID_DOB);
    CHECK(!rc_identifier_name("tfn", &bit) && !rc_identifier_name(NULL, &bit));
    CHECK(!rc_identifier_pattern(RC_ID_TFN) && rc_identifier_pattern(RC_ID_PHONE));
    puts("identifier tests passed");
    return 0;
}
