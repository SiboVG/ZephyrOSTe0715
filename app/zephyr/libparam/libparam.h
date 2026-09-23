#pragma once
/*
 * libparam csh/2.10 configuration for Zephyr. Matches the Linux profile of
 * fprime-csp-libparam (Config/libparam.h) so both sides use the same wire
 * format and API.
 */
#define PARAM_HAVE_SYS_QUEUE 1
#define PARAM_LIST_DYNAMIC 1
#define PARAM_LIST_POOL 0
#define PARAM_VMEM_64_BITS_API 1
#define PARAM_NUM_PUBLISHQUEUES 0
