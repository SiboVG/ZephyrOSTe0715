import importlib.util, sys
sys.path.insert(0, '/home/sibo-van-gool/Desktop/PhD/CubeSpec/FlightSoftware/ZephyrOS/cubespec-flight-software/verification/benches/zephyr-te0715/app/scripts')
p = '/home/sibo-van-gool/Desktop/PhD/CubeSpec/FlightSoftware/ZephyrOS/cubespec-flight-software/verification/benches/zephyr-te0715/app/scripts/sensor_bench.py'
spec = importlib.util.spec_from_file_location('sensor_bench', p); m = importlib.util.module_from_spec(spec)
sys.argv[0] = p; spec.loader.exec_module(m)
m.INA229_SPI_POINTS[:] = [(600000, 3), (1200000, 3), (2300000, 3), (4500000, 3), (9000000, 3)]
m.DEFAULT_SPI['ina'] = (1200000, 3)
sys.exit(m.main())
