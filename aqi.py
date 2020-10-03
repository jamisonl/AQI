import time
import board
import busio
from digitalio import DigitalInOut, Direction, Pull
import adafruit_pm25
from datetime import datetime
import os
import logging
from logging.handlers import TimedRotatingFileHandler
import asyncio
from typing import Tuple
from collections import defaultdict

reset_pin = None

i2c = busio.I2C(board.SCL, board.SDA, frequency=100000)
pm25Sensor = adafruit_pm25.PM25_I2C(i2c, reset_pin)
index_breakpoints = [[0, 50], [51, 100], [101, 150], [201, 300], [301, 500]]
pm25_breakpoints = [
    [0.0, 12.0],
    [12.1, 35.4],
    [35.5, 55.4],
    [55.5, 150.4],
    [150.5, 250.4],
    [250.5, 350.4],
    [350.5, 500.4],
]
pm10_breakpoints = [
    [0, 54],
    [55, 154],
    [155, 254],
    [255, 354],
    [355, 424],
    [425, 504],
    [505, 604],
]


def get_breakpoints(pmData, breakpoints_list) -> Tuple:
    for index, breakpoints in enumerate(breakpoints_list):
        if pmData >= breakpoints[0] and pmData <= breakpoints[1]:
            return index, breakpoints


def calc_aqi(
    pmData: float,
    pmType: str,
    index_breakpoints: list,
    pm25_breakpoints: list,
    pm10_breakpoints: list,
) -> int:
    if pmType == "pm25":
        cIndex, cBreakpoints = get_breakpoints(pmData, pm25_breakpoints)
        iBreakpoints = index_breakpoints[cIndex]
    if pmType == "pm10":
        cIndex, cBreakpoints = get_breakpoints(pmData, pm10_breakpoints)
        iBreakpoints = index_breakpoints[cIndex]
    # AQI piecewise function
    # AQI = (AQI breakpoint high - AQI breakpoint low / concentration breakpoint high - concentration breakpoint low) * (particulate matter concentration * concentration breakpoint low) + AQI breakpoint low
    aqi = (iBreakpoints[1] - iBreakpoints[0]) / (cBreakpoints[1] - cBreakpoints[0]) * (
        pmData - cBreakpoints[0]
    ) + iBreakpoints[0]
    return round(aqi)


async def create_timed_rotating_log(log_path):
    logger = logging.getLogger("Rotating Log")
    logger.setLevel(logging.INFO)
    handler = TimedRotatingFileHandler(log_path, when="d", interval=1, backupCount=5)

    logger.addHandler(handler)


def get_data():
    try:
        aqdata = pm25Sensor.read()
    except RuntimeError:
        print("sensor data error")
    try:
        # standard data
        pm10 = aqdata["pm10 standard"]
        pm25 = aqdata["pm25 standard"]
        pm100 = aqdata["pm100 standard"]

        sUnit10 = f"PM 1.0: {pm10}\n"
        sUnit25 = f"PM 2.5: {pm25}\n"
        sUnit100 = f"PM 10: {pm100}\n"

        # US EPA Air Quality Index
        aqi25 = calc_aqi(
            pm25, "pm25", index_breakpoints, pm25_breakpoints, pm10_breakpoints
        )
        aqi10 = calc_aqi(
            pm10, "pm10", index_breakpoints, pm25_breakpoints, pm10_breakpoints
        )

        aqiUnit25 = f"AQI 2.5: {aqi25}\n"
        aqiUnit10 = f"AQI 10: {aqi10}\n"

        # environmental data
        um3 = aqdata["particles 03um"]
        um5 = aqdata["particles 05um"]
        um10 = aqdata["particles 10um"]
        um25 = aqdata["particles 25um"]
        um50 = aqdata["particles 50um"]
        um100 = aqdata["particles 100um"]

        envUnit03um = f"Particles > 0.3um / 0.1L air: {um3}\n"
        envUnit05um = f"Particles > 0.5um / 0.1L air: {um5}\n"
        envUnit10um = f"Particles > 1.0 um / 0.1L air: {um10}\n"
        envUnit25um = f"Particles > 2.5um / 0.1L air: {um25}\n"
        envUnit50um = f"Particles > 5.0um / 0.1L air: {um50}\n"
        envUnit100um = f"Particles > 10 um / 0.1L air: {um100}\n"

        timestamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
        return {
            "sUnit10": sUnit10,
            "sUnit25": sUnit25,
            "sUnit100": sUnit100,
            "envUnit03um": envUnit03um,
            "envUnit05um": envUnit05um,
            "envUnit10um": envUnit10um,
            "envUnit25um": envUnit25um,
            "envUnit50um": envUnit50um,
            "envUnit100um": envUnit100um,
            "timestamp": timestamp,
            "aqiUnit25": aqiUnit25,
            "aqiUnit10": aqiUnit10,
            "pm10": pm10,
            "pm25": pm25,
            "pm100": pm100,
            "um3": um3,
            "um5": um5,
            "um10": um10,
            "um25": um25,
            "um50": um50,
            "um100": um100,
            "timestamp": timestamp,
            "aqi25": aqi25,
            "aqi10": aqi10,
        }
    except:
        return defaultdict(str)


# logs to stdout
def print_data(data):
    print("standard concentration units\n--------------------")
    print(f"{data['sUnit10']}{data['sUnit25']}{data['sUnit100']}")
    print("--------------------\nenvironmental units\n")
    print(
        f"{data['envUnit03um']}{data['envUnit05um']}{data['envUnit10um']}{data['envUnit25um']}{data['envUnit50um']}{data['envUnit100um']}"
    )
    print("--------------------\nUS EPA AQI\n")
    print(f"{data['aqiUnit10']}{data['aqiUnit25']}")
    print("\n\n")


def log_data(data, logging):
    logger = logging.getLogger("Rotating Log")
    logger.info(
        f"{data['timestamp']}\n {data['sUnit10']} {data['sUnit25']} {data['sUnit100']} {data['envUnit03um']} {data['envUnit05um']} {data['envUnit10um']} {data['envUnit25um']} {data['envUnit50um']} {data['aqiUnit10']} {data['aqiUnit25']}\n"
    )


async def print_process_loop(get_data, pm25Sensor, print_data):
    while True:
        await asyncio.sleep(1)
        data = get_data()
        print_data(data)


async def log_process_loop(get_data, pm25Sensor, log_data, logging):
    while True:
        await asyncio.sleep(10)
        data = get_data()
        log_data(data, logging)


async def main(
    create_timed_rotating_log,
    print_process_loop,
    log_process_loop,
    get_data,
    pm25Sensor,
    print_data,
    log_data,
    logging,
):
    await asyncio.gather(
        create_timed_rotating_log(os.path.expanduser("~/projects/aqi-server/log.log")),
        print_process_loop(get_data, pm25Sensor, print_data),
        log_process_loop(
            get_data,
            pm25Sensor,
            log_data,
            logging,
        ),
    )


if __name__ == "__main__":
    asyncio.run(
        main(
            create_timed_rotating_log,
            print_process_loop,
            log_process_loop,
            get_data,
            pm25Sensor,
            print_data,
            log_data,
            logging,
        )
    )