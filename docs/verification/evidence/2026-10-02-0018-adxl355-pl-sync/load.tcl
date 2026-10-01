# Same as the bench's xsdb.cfg, plus: report the L2 cache state before Zephyr
# starts, and optionally enable L2 the way U-Boot does (invalidate all ways, enable).
#   xsdb load.tcl <elf> <bit or -> <l2: keep|on>
lassign $argv elf bit l2 actlr
connect
targets -set -nocase -filter {name =~ "APU*"}
rst -system
after 1000
targets -set -nocase -filter {name =~ "*A9*#0"}
rst -processor
if {$bit ne "-"} { fpga -file $bit }
source /home/sibo-van-gool/Desktop/PhD/CubeSpec/FlightSoftware/ZephyrOS/cubespec-flight-software/verification/benches/zephyr-te0715/app/boards/trenz/te0715/support/ps7_init.tcl
ps7_init
ps7_post_config
proc rd {a} { return [format 0x%08X [expr {[mrd -force -value $a] & 0xFFFFFFFF}]] }
puts "before: L2_CONTROL [rd 0xF8F02100] L2_AUX [rd 0xF8F02104] ARM_CLK_CTRL [rd 0xF8000120] ARM_PLL [rd 0xF8000100]"
if {$l2 eq "on" && ([mrd -force -value 0xF8F02100] & 1) == 0} {
    mwr -force 0xF8F0277C 0xFFFF
    while {[mrd -force -value 0xF8F0277C] & 0xFFFF} { after 1 }
    mwr -force 0xF8F02100 1
}
if {$actlr ne ""} { rwr cp15 c1 actlr $actlr }
puts "start:  L2_CONTROL [rd 0xF8F02100] [lindex [split [rrd cp15 c1] \n] 0]"
dow $elf
con
disconnect
