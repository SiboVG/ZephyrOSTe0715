csp init
csp add can -c can0 -d 100
ping 6061
node 6061
list download
list
get bench_integer
get led_d4
set led_d4 1
get led_d4
sleep 2000
set led_d4 0
get led_d4
set bench_integer 42
get bench_integer
set bench_integer 305419896
get bench_integer
list forget 6061
list
list add -n 6061 -a 1 -m c bench_integer 200 uint32
list add -n 6061 -a 1 -m c led_d4 201 uint8
list
get bench_integer
get led_d4
set led_d4 1
get led_d4
sleep 2000
set led_d4 0
get led_d4
list forget 6061
