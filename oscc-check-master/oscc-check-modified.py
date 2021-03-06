#!/usr/bin/python3
"""Usage: oscc-check.py (-V <vehicle>) [-hdelv] [-b <bustype>] [-c <channel>]

Options:
    -h --help                            Display this information
    -V <vehicle>, --vehicle <vehicle>    Specify your vehicle. Required.
                                         (kia_soul_ev / kia_soul_petrol / kia_niro)
    -d --disable                         Disable modules only, no further checks (overrides enable)
    -e --enable                          Enable modules only, no further checks checks
    -l --loop                            Repeat all checks, run continuously
    -b --bustype <bustype>               CAN bus type [default: socketcan_native]
                                         (for more see https://python-can.readthedocs.io/en/2.1.0/interfaces.html)
    -c <channel>, --channel <channel>    Specify CAN channel, [default: can0]
    -v --version                         Display version information
"""

# This module lets us sleep intermittently. We're not in a hurry and want to see how the car behaves
# when commands are spaced out a bit.
import time

import csv
import os

# This module makes it easier to print colored text to stdout
# `Fore`` is used to set the color and `Style`` is used to reset to default.
import colorama
from colorama import Fore, Style

# This is a requirement for this tool's command line argument handling.
from docopt import docopt

# These are the local modules you would import if you wanted to use this tool as a library rather
# than an executable.
from oscccan.canbus import CanBus
from oscccan.canbus import Report
from oscccan import OsccModule


class DebugModules(object):
    """
    The 'DebugModules' class contains references to each of the OsccModules,
    brake, steering, and throttle. It is used to manage a majority of the stdout reporting this
    tool relies on.
    """

    def __init__(self, bus, brake, steering, throttle):
        """
        Initialize references to modules and CAN bus as well as the 'last_measurement' variable
        that allows this class to track whether expected increases and decreases occurred.
        """
        self.bus = bus
        self.brake = brake
        self.steering = steering
        self.throttle = throttle
        self.last_measurement = None

    def enable(self):
        """
        Enable all OSCC modules.
        """

        while True:

            success = self.enable_module(self.brake)

            if not success:
                continue

            success = self.enable_module(self.steering)

            if not success:
                continue

            success = self.enable_module(self.throttle)

            if not success:
                continue

            break

    def disable(self):
        """
        Disable all OSCC modules.
        """
        self.disable_module(self.brake)
        self.disable_module(self.steering)
        self.disable_module(self.throttle)

    def enable_module(self, module):
        """
        Enable a single OSCC modules. Print status, success and failure reports.
        """

        print(
            Fore.MAGENTA + ' status: ',
            Style.RESET_ALL,
            'attempting to enable',
            module.module_name,
            'module')

        # Attempt to enable the module parameter. Under the hood, this sends the enable brakes CAN
        # frame to OSCC/DriveKit over its CAN gateway.
        self.bus.enable_module(module)

        # Verify the module parameter is enabled by listening to the OSCC/DriveKit CAN gateway for
        # a status message that confirms it. Set the `success` flag so we can report and handle
        # failure
        success = self.bus.check_module_enabled_status(
            module,
            expect=True)

        if success:
            print(Fore.GREEN + ' success:', Style.RESET_ALL,
                  module.module_name, 'module enabled')
        else:
            print(
                Fore.RED +
                ' error:  ',
                Style.RESET_ALL,
                module.module_name,
                'module could not be enabled')

        self.bus.reading_sleep()

        return success

    def disable_module(self, module):
        """
        Disable a single OSCC modules. Print status, success and failure reports.
        """

        print(
            Fore.MAGENTA + ' status: ',
            Style.RESET_ALL,
            'attempting to disable',
            module.module_name,
            'module')

        # Attempt to disable the module parameter. Under the hood, this sends the disable brakes CAN
        # frame to OSCC/DriveKit over its CAN gateway.
        self.bus.disable_module(module)

        time.sleep(1)

        # Verify the module parameter is disabled by listening to the OSCC/DriveKit CAN gateway for
        # a status message that confirms it. Set the `success` flag so we can report and handle
        # failure
        success = self.bus.check_module_enabled_status(
            module,
            expect=False)

        if success:
            print(Fore.GREEN + ' success:', Style.RESET_ALL,
                  module.module_name, 'module disabled')
            return True
        else:
            print(
                Fore.RED + ' error:  ',
                Style.RESET_ALL,
                module.module_name,
                'module could not be disabled')
            return False

    def command_brake_module(self, cmd_value, expect=None):
        """
        Command OSCC brake module and verify resulting behavior. Print status, success and
        failure reports.
        """

        if expect is not None:
            print(
                Fore.MAGENTA + ' status: ',
                Style.RESET_ALL,
                'attempting to',
                expect,
                'brake pressure from',
                self.last_measurement, 'bar')

        print(
            Fore.MAGENTA + ' status: ',
            Style.RESET_ALL,
            'sending command value',
            cmd_value,
            'to brake module')
        self.bus.send_command(self.brake, cmd_value, timeout=1.0)

        self.bus.reading_sleep()

        print(Fore.MAGENTA + ' status: ',
              Style.RESET_ALL, 'measuring brake pressure')

        if expect == 'increase':
            report = self.bus.check_brake_pressure(
                timeout=1.0, increase_from=self.last_measurement)
        elif expect == 'decrease':
            report = self.bus.check_brake_pressure(
                timeout=1.0, decrease_from=self.last_measurement)
        else:
            report = self.bus.check_brake_pressure(timeout=1.0)

        if report.success is True:
            print(
                Fore.GREEN + ' success:',
                Style.RESET_ALL,
                'brake pressure measured at',
                report.value,
                'bar')
        else:
            if report.value is not None and expect is not None:
                print(
                    Fore.YELLOW + ' unexpected:',
                    Style.RESET_ALL,
                    'brake pressure measured at',
                    report.value,
                    '(did not measure',
                    expect,
                    'from last measurement',
                    self.last_measurement,
                    ')')
            else:
                print(Fore.RED + ' error:  ', Style.RESET_ALL,
                      'failed to read brake pressure')

        self.last_measurement = report.value

        self.bus.reading_sleep()
    def orient_to_angle(self, goal_angle, steering_ratio=1, debug=True): #goal angle is desired drive wheel angle
        goal_angle *= steering_ratio
        angle_tolerance = 2
        standard_torque_positive = 0.05
        standard_torque_negative = -0.05
        angles = [self.bus.check_steering_wheel_angle().value]
        with open("tests/orient/orient_to_angle_test_{}".format(len(os.listdir("tests/orient"))), "w") as csvfile:
            fieldnames = ["Torque", "Change in Angle", "New Angle", "Goal Angle"]
            writer = csv.DictWriter(csvfile, fieldnames)

            while abs(goal_angle - self.bus.check_steering_wheel_angle().value) < angle_tolerance:
                angle = angles[-1]
                if angle < goal_angle:
                    torque = standard_torque_positive
                elif angle > goal_angle:
                    torque = standard_torque_negative
                self.command_steering_module(torque)
                angle = self.bus_check_steering_wheel_angle().value
                angles.append(angle)
                if debug:
                    writer.writerow({"Torque":torque, "New Angle":angles[-1], "Change in Angle":angles[-1]-angles[-2], "Goal Angle":goal_angle})

    def command_steering_module(self, cmd_value, expect=None):
        """
        Command OSCC steering module and verify resulting behavior. Print status, success and
        failure reports.
        """

        if expect is not None:
            direction = 'positive' if expect == 'increase' else 'negative'
            print(
                Fore.MAGENTA + ' status: ',
                Style.RESET_ALL,
                direction,
                'torque applied to steering wheel')

        print(
            Fore.MAGENTA + ' status: ',
            Style.RESET_ALL,
            'sending command value',
            cmd_value,
            'to steering module')
        self.bus.send_command(self.steering, cmd_value, timeout=1.0)

        self.bus.reading_sleep()

        print(Fore.MAGENTA + ' status: ', Style.RESET_ALL,
              'measuring steering wheel angle')

        report = Report()
        report.success = False
        if expect == 'increase':
            report = self.bus.check_steering_wheel_angle(
                timeout=1.0,
                increase_from=self.last_measurement)
        elif expect == 'decrease':
            report = self.bus.check_steering_wheel_angle(
                timeout=1.0,
                decrease_from=self.last_measurement)
        else:
            report = self.bus.check_steering_wheel_angle(timeout=1.0)

        if report.success is True:
            print(
                Fore.GREEN + ' success:',
                Style.RESET_ALL,
                'steering wheel angle measured at',
                str(report.value) + '°')

        else:
            if report.value is not None and expect is not None:
                print(
                    Fore.YELLOW + ' unexpected:',
                    Style.RESET_ALL,
                    'steering wheel angle measured at',
                    report.value,
                    '(did not measure', expect,
                    'from last measurement',
                    str(self.last_measurement) + '°)')
            else:
                print(
                    Fore.RED + ' error:  ',
                    Style.RESET_ALL,
                    'failed to read steering wheel angle')

        self.last_measurement = report.value

        self.bus.reading_sleep()

        if report.success is True:
            return report.value

    def command_throttle_module(self, cmd_value, expect=None):
        """
        Command OSCC throttle module and verify resulting behavior. Print status, success and
        failure reports.
        """

        if expect is not None:
            print(
                Fore.RED + ' unexpected:',
                Style.RESET_ALL,
                'no logic to measure',
                expect,
                'in wheel speed')

        print(
            Fore.MAGENTA + ' status: ',
            Style.RESET_ALL,
            'sending command value',
            cmd_value,
            'to throttle module')

        self.bus.send_command(self.throttle, cmd_value, timeout=1.0)

        print(Fore.MAGENTA + ' status:',
              Style.RESET_ALL, ' measuring wheel speed')

        report = self.bus.check_wheel_speed(timeout=1.0)

        if report.success is True and report.value is not None:
            print(
                Fore.GREEN + ' success:', Style.RESET_ALL,
                'wheel speeds measured at lf', str(report.value[0]) +
                ', rf', str(report.value[1]) +
                ', lr', str(report.value[2]) +
                ', rr', str(report.value[3]))
        else:
            print(Fore.RED + ' error:', Style.RESET_ALL,
                  '  failed to read wheel speeds')

        self.last_measurement = report.value

        self.bus.reading_sleep()


def check_vehicle_arg(arg):
    """
    Sanity check the optional vehicle argument.
    """

    vehicles = ['kia_soul_ev', 'kia_soul_petrol', 'kia_niro', None]
    if arg not in vehicles:
        raise ValueError('Unable to target vehicle',
                         arg + '. Options are', vehicles)


def main(args):
    if args['--version']:
        print('oscc-check 0.0.2')
        return

    check_vehicle_arg(args['--vehicle'])

    bus = CanBus(
        vehicle=args['--vehicle'],
        bustype=args['--bustype'],
        channel=args['--channel'])

    brakes = OsccModule(base_arbitration_id=0x70, module_name='brake')
    steering = OsccModule(base_arbitration_id=0x80, module_name='steering')
    throttle = OsccModule(base_arbitration_id=0x90, module_name='throttle')
    #steering_angle = OsccModule(base_arbitration_id=0x2B0, module_name="steering_angle")


    modules = DebugModules(bus, brakes, steering, throttle)

    # Initialize module for printing colored text to stdout
    colorama.init()

    if args['--disable']:
        modules.disable()
        return
    elif args['--enable']:
        modules.enable()
        return

    # Each section or step of the following loop is distinguished from the next by this separator.
    # The output begins with this separator for visually consistent output.
    print("|Enable Modules -----------------------------------------------------------------|")

    # This `while` loop repeats the same basic steps on each iteration, they are as follows:
    # 1. Enable each OSCC module.
    # 2. Send commands to increase and decrease brake pressure.
    # 3. Verify that brake pressure reported by vehicle increased or decreased accordingly.
    # 4. Send commands to apply positive or negative torque to steering wheel.
    # 5. Verify that the steering wheel angle increased or decreased accordingly.
    # 6. Disable each OSCC module.
    while True:

        modules.enable()


        # Visually distinguish brake validation from the following steering wheel validation
        print("|Steering Test ------------------------------------------------------------------|")
        STEERING_RATIO = 1/15.7
        file_num = len(os.listdir("tests")) + 7
        fieldnames = ["Torque", "New Angle", "Change in Angle", "Goal Angle"]
        with open("torque_test_space2{}.csv".format(file_num), "w") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            angles = [modules.bus.check_steering_wheel_angle().value]
            current = 0
            max_torque = 0.25
            step = 0.05
            previous = 0
            num_steps = max_torque/step + 1
            i = -1
            for n in range(int(num_steps)):
                for j in range(3):
                    if j == 0:
                        print("j = 0")
                    elif j == 1:
                        print("j = 1")
                    elif j == 2:
                        print("j = 2")
                    if j == 0:
                        for k in range(3):
                            torque_cmd = current
                            print("torque = " + str(torque_cmd))
                            try:
                                angles.append(modules.command_steering_module(torque_cmd, expect=None))
                            except:
                                raise Exception("Steering angle function error")
                            writer.writerow({"Torque":torque_cmd, "New Angle":angles[i], "Change in Angle":angles[i]-angles[i-1], "Goal Angle": "n/a"})
                    elif j == 1:
                        if current != 0:
                            for k in range(3):
                                torque_cmd = 0
                                print("torque = " + str(torque_cmd))
                                try:
                                    angles.append(modules.command_steering_module(torque_cmd, expect=None))
                                except:
                                    raise Exception("Steering angle function error")
                                writer.writerow({"Torque":torque_cmd, "New Angle":angles[i], "Change in Angle":angles[i]-angles[i-1], "Goal Angle": "n/a"})
                        else:
                            print("already tested 0")
                    elif j == 2:
                        if current != 0:
                            for k in range(3):
                                torque_cmd = -current
                                print("torque = " + str(torque_cmd))
                                try:
                                    angles.append(modules.command_steering_module(torque_cmd, expect=None))
                                except:
                                    raise Exception("Steering angle function error")
                                writer.writerow({"Torque":torque_cmd, "New Angle":angles[i], "Change in Angle":angles[i]-angles[i-1], "Goal Angle": "n/a"})
                        else:
                            print("already tested 0")

                if -max_torque < current < max_torque:
                    current += step



        '''
        PolySync's Original Test Code

        torque_cmd = -0.1
        modules.command_steering_module(torque_cmd, expect=None)

        torque_cmd = 0.1
        modules.command_steering_module(torque_cmd, expect=None)

        torque_cmd = 0.15
        modules.command_steering_module(torque_cmd, expect='increase')

        torque_cmd = -0.15
        modules.command_steering_module(torque_cmd, expect='decrease')
        '''
        # Visually distinguish enable steps from the following brake validation
        print("|Brake Test --------------------------------------------------------------------|")

        pressure_cmd = 0.0
        modules.command_brake_module(pressure_cmd, expect=None)

        pressure_cmd = 0.5
        modules.command_brake_module(pressure_cmd, expect='increase')

        pressure_cmd = 0.0
        modules.command_brake_module(pressure_cmd, expect='decrease')

        pressure_cmd = 0.3
        modules.command_brake_module(pressure_cmd, expect='increase')

        pressure_cmd = 0.0
        modules.command_brake_module(pressure_cmd, expect='decrease')
        # Visually distinguish throttle validation from the following disable steps
        print("|Disable Modules ----------------------------------------------------------------|")

        modules.disable()

        if not args['--loop']:
            break

        # Visually distinguish disable steps from the following enable steps
        print("|Enable Modules -----------------------------------------------------------------|")


if __name__ == "__main__":
    """
    The program's entry point if run as an executable.
    """

    main(docopt(__doc__))
