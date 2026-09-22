#include <zephyr/kernel.h>
#include <stdio.h>

int main(void)
{
    while (1) {
        printf("Hello from Trenz TE0715 running Zephyr OS!\n");
        k_msleep(1000);
    }
    return 0;
}

