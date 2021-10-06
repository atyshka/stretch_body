from __future__ import print_function
from math import *
from stretch_body.stepper import *
from stretch_body.device import Device
from stretch_body.trajectories import DiffDriveTrajectory
from stretch_body.hello_utils import *
import logging
import numpy

class Base(Device):
    """
    API to the Stretch RE1 Mobile Base
    """
    def __init__(self):
        Device.__init__(self, 'base')
        self.left_wheel = Stepper(usb='/dev/hello-motor-left-wheel')
        self.right_wheel = Stepper(usb='/dev/hello-motor-right-wheel')
        self.status = {'timestamp_pc':0,'x':0,'y':0,'theta':0,'x_vel':0,'y_vel':0,'theta_vel':0, 'pose_time_s':0,'effort': [0, 0], 'left_wheel': self.left_wheel.status, 'right_wheel': self.right_wheel.status, 'translation_force': 0, 'rotation_torque': 0}
        self.trajectory = DiffDriveTrajectory()
        self._waypoint_lwpos = None
        self._waypoint_rwpos = None
        self.thread_rate_hz = 5.0
        self.first_step=True
        wheel_circumference_m = self.params['wheel_diameter_m'] * pi
        self.meters_per_motor_rad = (wheel_circumference_m / (2.0 * pi)) / self.params['gr']
        self.wheel_separation_m = self.params['wheel_separation_m']

        # Default controller params
        self.stiffness=1.0
        self.vel_mr=self.translate_to_motor_rad(self.params['motion']['default']['vel_m'])
        self.accel_mr=self.translate_to_motor_rad(self.params['motion']['default']['accel_m'])
        self.i_contact_l, self.i_contact_r=self.translation_force_to_motor_current(self.params['contact_thresh_N'])
        self.fast_motion_allowed = True
    # ###########  Device Methods #############

    def startup(self, threaded=False):
        Device.startup(self, threaded=threaded)
        success=self.left_wheel.startup(threaded=False) and self.right_wheel.startup(threaded=False)
        self.__update_status()
        return success

    def _thread_loop(self):
        self.pull_status()
        self.update_trajectory()

    def stop(self):
        Device.stop(self)
        if self.left_wheel.hw_valid and int(str(self.left_wheel.board_info['protocol_version'])[1:]) >= 1:
            self.left_wheel.stop_waypoint_trajectory()
            self._waypoint_lwpos = None
        if self.right_wheel.hw_valid and int(str(self.right_wheel.board_info['protocol_version'])[1:]) >= 1:
            self.right_wheel.stop_waypoint_trajectory()
            self._waypoint_rwpos = None
        self.left_wheel.stop()
        self.right_wheel.stop()

    def pretty_print(self):
        print('----------Base------')
        print('X (m)',self.status['x'])
        print('Y (m)',self.status['y'])
        print('Theta (rad)',self.status['theta'])
        print('X_vel (m/s)', self.status['x_vel'])
        print('Y_vel (m/s)', self.status['y_vel'])
        print('Theta_vel (rad/s)', self.status['theta_vel'])
        print('Pose time (s)', self.status['pose_time_s'])
        print('Translation Force (N)',self.status['translation_force'])
        print('Rotation Torque (Nm)', self.status['rotation_torque'])
        print('Timestamp PC (s):', self.status['timestamp_pc'])
        print('-----Left-Wheel-----')
        self.left_wheel.pretty_print()
        print('-----Right-Wheel-----')
        self.right_wheel.pretty_print()

    # ###################################################
    def enable_freewheel_mode(self):
        """
        Force motors into freewheel
        """
        self.left_wheel.enable_freewheel()
        self.right_wheel.enable_freewheel()

    def enable_pos_incr_mode(self):
        """
                Force motors into incremental position mode
        """
        self.left_wheel.enable_pos_traj_incr()
        self.right_wheel.enable_pos_traj_incr()

    # ###################################################

    def translate_by(self, x_m, v_m=None, a_m=None, stiffness=None, contact_thresh_N=None):
        """
        Incremental translation of the base
        x_m: desired motion (m)
        v_m: velocity for trapezoidal motion profile (m/s)
        a_m: acceleration for trapezoidal motion profile (m/s^2)
        stiffness: stiffness of motion. Range 0.0 (min) to 1.0 (max)
        contact_thresh_N: force threshold to stop motion (TODO: Not yet implemented)
        """
        x_mr = self.translate_to_motor_rad(x_m)

        if v_m is not None:
            v_m = min(abs(v_m), self.params['motion']['max']['vel_m'])
            v_mr = self.translate_to_motor_rad(v_m)
        else:
            v_mr = self.vel_mr

        if a_m is not None:
            a_m = min(abs(a_m), self.params['motion']['max']['accel_m'])
            a_mr = self.translate_to_motor_rad(a_m)
        else:
            a_mr = self.accel_mr

        if not self.fast_motion_allowed:
            v_mr=min(self.translate_to_motor_rad(self.params['sentry_max_velocity']['limit_vel_m']),v_mr)
            a_mr=min(self.translate_to_motor_rad(self.params['sentry_max_velocity']['limit_accel_m']),a_mr)

        if contact_thresh_N is None:
            i_contact_l=self.i_contact_l
            i_contact_r=self.i_contact_r
        else:
            i_contact_l, i_contact_r = self.translation_force_to_motor_current(min(self.params['contact_thresh_max_N'],contact_thresh_N))

        if stiffness is None:
            stiffness=self.stiffness



        self.left_wheel.set_command(mode=Stepper.MODE_POS_TRAJ_INCR, x_des=x_mr,
                                    v_des=v_mr,
                                    a_des=a_mr,
                                    stiffness=stiffness,
                                    i_feedforward=0,
                                    i_contact_pos=i_contact_l,
                                    i_contact_neg=-1*i_contact_l)
        self.right_wheel.set_command(mode=Stepper.MODE_POS_TRAJ_INCR, x_des=x_mr,
                                    v_des=v_mr,
                                    a_des=a_mr,
                                    stiffness=stiffness,
                                    i_feedforward=0,
                                    i_contact_pos=i_contact_r,
                                    i_contact_neg=-1*i_contact_r)


    def rotate_by(self, x_r, v_r=None, a_r=None, stiffness=None, contact_thresh_N=None):
        """
        Incremental rotation of the base
        x_r: desired motion (radians)
        v_r: velocity for trapezoidal motion profile (rad/s)
        a_r: acceleration for trapezoidal motion profile (rad/s^2)
        stiffness: stiffness of motion. Range 0.0 (min) to 1.0 (max)
        contact_thresh_N: force threshold to stop motion (Not yet implemented)
        """
        x_mr = self.rotate_to_motor_rad(x_r)

        if v_r is not None:
            v_mr_max = self.translate_to_motor_rad(self.params['motion']['max']['vel_m'])
            v_mr = self.rotate_to_motor_rad(v_r)
            v_mr=min(abs(v_mr),v_mr_max)
        else:
            v_mr = self.vel_mr

        if a_r is not None:
            a_mr_max = self.translate_to_motor_rad(self.params['motion']['max']['accel_m'])
            a_mr = self.rotate_to_motor_rad(a_r)
            a_mr = min(abs(a_mr), a_mr_max)
        else:
            a_mr = self.accel_mr

        if not self.fast_motion_allowed:
            v_mr=min(self.translate_to_motor_rad(self.params['sentry_max_velocity']['limit_vel_m']),v_mr)
            a_mr=min(self.translate_to_motor_rad(self.params['sentry_max_velocity']['limit_accel_m']),a_mr)



        if contact_thresh_N is None:
            i_contact_l = self.i_contact_l
            i_contact_r = self.i_contact_r
        else:
            i_contact_l, i_contact_r = self.rotation_torque_to_motor_current(min(self.params['contact_thresh_max_N'],contact_thresh_N))

        if stiffness is None:
            stiffness = self.stiffness
        self.left_wheel.set_command(mode=Stepper.MODE_POS_TRAJ_INCR,x_des=-1*x_mr,
                                    v_des=v_mr,
                                    a_des=a_mr,
                                    stiffness=stiffness,
                                    i_feedforward=0,
                                    i_contact_pos=i_contact_l,
                                    i_contact_neg=-1 * i_contact_l)
        self.right_wheel.set_command(mode=Stepper.MODE_POS_TRAJ_INCR,x_des=x_mr,
                                     v_des=v_mr,
                                     a_des=a_mr,
                                     stiffness=stiffness,
                                     i_feedforward=0,
                                     i_contact_pos=i_contact_r,
                                     i_contact_neg=-1 * i_contact_r)



    def set_translate_velocity(self, v_m, a_m=None):
        """
        Command the bases translational velocity.
        Use care to prevent collisions / avoid runaways
        v_m: desired velocity (m/s)
        a_m: acceleration of motion profile (m/s^2)
        """
        if a_m is not None:
            a_m = min(abs(a_m), self.params['motion']['max']['accel_m'])
            a_mr = self.translate_to_motor_rad(a_m)
        else:
            a_mr = self.accel_mr
        v_sign = numpy.sign(v_m)
        v_m = v_sign * min(abs(v_m), self.params['motion']['max']['vel_m'])
        v_mr = self.translate_to_motor_rad(v_m)
        self.left_wheel.set_command(mode=Stepper.MODE_VEL_TRAJ, v_des=v_mr, a_des=a_mr)
        self.right_wheel.set_command(mode=Stepper.MODE_VEL_TRAJ, v_des=v_mr, a_des=a_mr)

    def set_rotational_velocity(self, v_r, a_r=None):
        """
        Command the bases rotational velocity.
        Use care to prevent collisions / avoid runaways
        v_r: desired rotational velocity (rad/s)
        a_r: acceleration of motion profile (rad/s^2)
        """
        if a_r is not None:
            a_mr_max=self.translate_to_motor_rad(self.params['motion']['max']['accel_m'])
            a_mr = self.rotate_to_motor_rad(a_r)
            a_mr = min(abs(a_mr), a_mr_max)
        else:
            a_mr = self.accel_mr

        w_sign = numpy.sign(v_r)
        v_mr_max = self.translate_to_motor_rad(self.params['motion']['max']['vel_m'])
        v_mr = self.rotate_to_motor_rad(v_r)
        v_mr = w_sign * min(abs(v_mr), v_mr_max)
        self.left_wheel.set_command(mode=Stepper.MODE_VEL_TRAJ, v_des=-1*v_mr, a_des=a_mr)
        self.right_wheel.set_command(mode=Stepper.MODE_VEL_TRAJ, v_des=v_mr, a_des=a_mr)

    def set_velocity(self, v_m, w_r, a=None):
        """
        Command the bases translational and rotational
        velocities simultaneously.
        Use care to prevent collisions / avoid runaways
        v_m: desired velocity (m/s)
        w_r: desired rotational velocity (rad/s)
        a:   acceleration of motion profile (m/s^2 and rad/s^2)
        """
        if a is not None:
            a = min(abs(a), self.params['motion']['max']['accel_m'])
            a_mr = self.translate_to_motor_rad(a)
        else:
            a_mr = self.accel_mr

        # Unicycle dynamics w/o R because
        # translate_to_motor_rad accounts for R and gear ratio
        wl_m = ((2 * v_m) - (w_r * self.params['wheel_separation_m'])) / 2.0
        wr_m = ((2 * v_m) + (w_r * self.params['wheel_separation_m'])) / 2.0

        wl_sign = numpy.sign(wl_m)
        wl_m = wl_sign * min(abs(wl_m), self.params['motion']['max']['vel_m'])
        wl_r = self.translate_to_motor_rad(wl_m)

        wr_sign = numpy.sign(wr_m)
        wr_m = wr_sign * min(abs(wr_m), self.params['motion']['max']['vel_m'])
        wr_r = self.translate_to_motor_rad(wr_m)

        self.left_wheel.set_command(mode=Stepper.MODE_VEL_TRAJ, v_des=wl_r, a_des=a_mr)
        self.right_wheel.set_command(mode=Stepper.MODE_VEL_TRAJ, v_des=wr_r, a_des=a_mr)

    # ######### Waypoint Trajectory Interface ##############################

    def follow_trajectory(self, v_r=None, a_r=None, stiffness=None, contact_thresh_N=None):
        """Starts executing a waypoint trajectory

        `self.trajectory` must be populated with a valid trajectory before calling
        this method.

        Parameters
        ----------
        v_r : float
            velocity limit for trajectory in motor space in meters per second
        a_r : float
            acceleration limit for trajectory in motor space in meters per second squared
        stiffness : float
            stiffness of motion. Range 0.0 (min) to 1.0 (max)
        contact_thresh_N : float
            force threshold to stop motion (~Newtons)
        """
        # check if joint valid, traj active, and right protocol
        if not self.left_wheel.hw_valid or not self.right_wheel.hw_valid:
            self.logger.warning('Base connection to hardware not valid')
            return
        if self._waypoint_lwpos is not None or self._waypoint_rwpos is not None:
            self.logger.warning('Base waypoint trajectory already active')
            return
        if int(str(self.left_wheel.board_info['protocol_version'])[1:]) < 1:
            self.logger.warning("Base left motor firmware version doesn't support waypoint trajectories")
            return
        if int(str(self.right_wheel.board_info['protocol_version'])[1:]) < 1:
            self.logger.warning("Base right motor firmware version doesn't support waypoint trajectories")
            return

        # check if trajectory valid
        vel_limit = v_r if v_r is not None else self.params['motion']['trajectory_max']['vel_r']
        acc_limit = a_r if a_r is not None else self.params['motion']['trajectory_max']['accel_r']
        valid, reason = self.trajectory.is_valid(vel_limit, acc_limit, self.translate_to_motor_rad, self.rotate_to_motor_rad)
        if not valid:
            self.logger.warning('Base trajectory not valid: {0}'.format(reason))
            return

        # set defaults
        stiffness = max(0, min(1.0, stiffness)) if stiffness is not None else self.stiffness
        v = self.translate_to_motor_rad(min(abs(v_r), self.params['motion']['trajectory_max']['vel_r'])) \
            if v_r is not None else self.translate_to_motor_rad(self.params['motion']['trajectory_max']['vel_r'])
        a = self.translate_to_motor_rad(min(abs(a), self.params['motion']['trajectory_max']['accel_r'])) \
            if a_r is not None else self.translate_to_motor_rad(self.params['motion']['trajectory_max']['accel_r'])
        i_contact_l, i_contact_r = self.translation_force_to_motor_current(min(contact_thresh_N, self.params['contact_thresh_max_N'])) \
            if contact_thresh_N is not None else self.translation_force_to_motor_current(self.params['contact_thresh_N'])

        # start trajectory
        self.left_wheel.set_command(mode=Stepper.MODE_POS_TRAJ_WAYPOINT,
                                    v_des=v,
                                    a_des=a,
                                    stiffness=stiffness,
                                    i_contact_pos=i_contact_l,
                                    i_contact_neg=-i_contact_l)
        self.right_wheel.set_command(mode=Stepper.MODE_POS_TRAJ_WAYPOINT,
                                     v_des=v,
                                     a_des=a,
                                     stiffness=stiffness,
                                     i_contact_pos=i_contact_r,
                                     i_contact_neg=-i_contact_r)
        self.left_wheel.push_command()
        self.right_wheel.push_command()
        self.left_wheel.pull_status()
        self.right_wheel.pull_status()
        self._waypoint_lwpos = self.left_wheel.status['pos']
        self._waypoint_rwpos = self.right_wheel.status['pos']
        ls0, rs0 = self.trajectory.get_wheel_segments(0, self.translate_to_motor_rad, self.rotate_to_motor_rad,
            self._waypoint_lwpos, self._waypoint_rwpos)
        self.left_wheel.start_waypoint_trajectory(ls0.to_array())
        self.right_wheel.start_waypoint_trajectory(rs0.to_array())

    def update_trajectory(self):
        """Updates hardware with the next segment of `self.trajectory`

        This method must be called frequently to enable complete trajectory execution
        and preemption of future segments. If used with `stretch_body.robot.Robot` or
        with `self.startup(threaded=True)`, a background thread is launched for this.
        Otherwise, the user must handle calling this method.
        """
        # check if joint valid, right protocol, and right mode
        if not self.left_wheel.hw_valid or not self.right_wheel.hw_valid:
            return
        if int(str(self.left_wheel.board_info['protocol_version'])[1:]) < 1:
            return
        if int(str(self.right_wheel.board_info['protocol_version'])[1:]) < 1:
            return
        if self.left_wheel.status['mode'] != self.left_wheel.MODE_POS_TRAJ_WAYPOINT:
            return
        if self.right_wheel.status['mode'] != self.right_wheel.MODE_POS_TRAJ_WAYPOINT:
            return

        if self.left_wheel.status['waypoint_traj']['state'] == 'active':
            next_segment_id = self.left_wheel.status['waypoint_traj']['segment_id'] - 2 + 1 # subtract 2 due to IDs 0 & 1 being reserved by firmware
            if next_segment_id < self.trajectory.get_num_segments():
                ls1, _ = self.trajectory.get_wheel_segments(next_segment_id, self.translate_to_motor_rad, self.rotate_to_motor_rad,
                    self._waypoint_lwpos, self._waypoint_rwpos)
                self.left_wheel.set_next_trajectory_segment(ls1.to_array())
        elif self.left_wheel.status['waypoint_traj']['state'] == 'idle' and self.left_wheel.status['mode'] == Stepper.MODE_POS_TRAJ_WAYPOINT:
            self.left_wheel.enable_pos_traj()
            self.push_command()

        if self.right_wheel.status['waypoint_traj']['state'] == 'active':
            next_segment_id = self.right_wheel.status['waypoint_traj']['segment_id'] - 2 + 1 # subtract 2 due to IDs 0 & 1 being reserved by firmware
            if next_segment_id < self.trajectory.get_num_segments():
                _, rs1 = self.trajectory.get_wheel_segments(next_segment_id, self.translate_to_motor_rad, self.rotate_to_motor_rad,
                    self._waypoint_lwpos, self._waypoint_rwpos)
                self.right_wheel.set_next_trajectory_segment(rs1.to_array())
        elif self.right_wheel.status['waypoint_traj']['state'] == 'idle' and self.right_wheel.status['mode'] == Stepper.MODE_POS_TRAJ_WAYPOINT:
            self.right_wheel.enable_pos_traj()
            self.push_command()

    def step_sentry(self,robot):
        """
        Only allow fast mobile base motion if the lift is low,
        the arm is retracted, and the wrist is stowed. This is
        intended to keep the center of mass low for increased
        stability and avoid catching the arm or tool on
        something.
        """
        if self.robot_params['robot_sentry']['base_max_velocity']:
            x_lift=robot.lift.status['pos']
            x_arm =robot.arm.status['pos']
            x_wrist =robot.end_of_arm.motors['wrist_yaw'].status['pos']

            if ((x_lift < self.params['sentry_max_velocity']['max_lift_height_m']) and
                    (x_arm < self.params['sentry_max_velocity']['max_arm_extension_m']) and
                    (x_wrist > self.params['sentry_max_velocity']['min_wrist_yaw_rad'])):
                if not self.fast_motion_allowed:
                    self.logger.debug('Fast motion turned on')
                self.fast_motion_allowed = True
            else:
                if self.fast_motion_allowed:
                    self.logger.debug('Fast motion turned off')
                self.fast_motion_allowed = False

        self.left_wheel.step_sentry(robot)
        self.right_wheel.step_sentry(robot)

    # ###################################################
    def push_command(self):
        self.left_wheel.push_command()
        self.right_wheel.push_command()

    def pull_status(self):
        """
        Computes base odometery based on stepper positions / velocities
        """
        self.left_wheel.pull_status()
        self.right_wheel.pull_status()
        self.__update_status()

    def __update_status(self):
        self.status['timestamp_pc'] = time.time()

        p0 = self.status['left_wheel']['pos']
        p1 = self.status['right_wheel']['pos']
        v0 = self.status['left_wheel']['vel']
        v1 = self.status['right_wheel']['vel']
        e0 = self.status['left_wheel']['effort']
        e1 = self.status['right_wheel']['effort']
        t0 = self.status['left_wheel']['timestamp']
        t1 = self.status['right_wheel']['timestamp']
        self.status['translation_force'] = self.motor_current_to_translation_force(self.left_wheel.status['current'],self.right_wheel.status['current'])
        self.status['rotation_torque'] = self.motor_current_to_rotation_torque(self.left_wheel.status['current'],self.right_wheel.status['current'])

        if self.first_step:
            # Upon the first step, simply set the initial pose, since
            # no movement has yet been recorded.
            self.first_step = False

            self.p0 = p0
            self.p1 = p1

            self.t0_s = t0
            self.t1_s = t1

            self.status['x'] = 0.0
            self.status['y'] = 0.0
            self.status['theta'] = 0.0

            self.status['x_vel'] = 0.0
            self.status['y_vel'] = 0.0
            self.status['theta_vel'] = 0.0

        else:
            ######################################################
            # The odometry related was wrtten starting on January 14,
            # 2019 whle looking at the following BSD-3-Clause licensed
            # code for reference.

            # https://github.com/merose/diff_drive/blob/master/src/diff_drive/odometry.py

            # The code uses standard calculations. The reference code
            # specifically cites a document with the following link,
            # which appears to be broken.

            # https://chess.eecs.berkeley.edu/eecs149/documentation/differentialDrive.pdf

            # There are many sources on the internet for these
            # equations. For example, the following document is
            # helpful:

            # http://www8.cs.umu.se/kurser/5DV122/HT13/material/Hellstrom-ForwardKinematics.pdf

            prev_t0_s = self.t0_s
            prev_t1_s = self.t1_s
            t0_s = t0
            t1_s = t1

            delta_t0_s = t0_s - prev_t0_s
            delta_t1_s = t1_s - prev_t1_s

            if (delta_t0_s > 0.0) and (delta_t1_s > 0.0):
                # update if time has passed for both motor readings, otherwise do nothing

                average_delta_t_s = (delta_t0_s + delta_t1_s) / 2.0

                # update the times, since both motors have new readings
                self.prev_t0_s = self.t0_s
                self.prev_t1_s = self.t1_s
                self.t0_s = t0_s
                self.t1_s = t1_s

                # need to check on wrap around / rollover for wheel positions
                self.prev_p0 = self.p0
                self.prev_p1 = self.p1
                self.p0 = p0
                self.p1 = p1

                # Transform the wheel rotations so that left and right
                # wheel distances in meters have the convention that
                # positive values for each wheel corresponds with forward
                # motion of the mobile base.
                prev_left_m = self.prev_p0 * self.meters_per_motor_rad
                left_m = self.p0 * self.meters_per_motor_rad

                prev_right_m = self.prev_p1 * self.meters_per_motor_rad
                right_m = self.p1 * self.meters_per_motor_rad

                delta_left_m = left_m - prev_left_m
                delta_right_m = right_m - prev_right_m

                delta_travel = (delta_right_m + delta_left_m) / 2.0
                delta_theta = (delta_right_m - delta_left_m) / self.wheel_separation_m

                prev_x = self.status['x']
                prev_y = self.status['y']
                prev_theta = self.status['theta']

                if delta_left_m == delta_right_m:
                    # delta_theta is 0.0, which would result in a divide
                    # by zero error and corresponds with an infinite
                    # radius of curvature (0 curvature).
                    delta_x = delta_travel * cos(prev_theta)
                    delta_y = delta_travel * sin(prev_theta)
                else:
                    # calculate the instantaneous center of curvature (ICC)
                    icc_radius = delta_travel / delta_theta
                    icc_x = prev_x - (icc_radius * sin(prev_theta))
                    icc_y = prev_y + (icc_radius * cos(prev_theta))

                    # calculate the change in position based on the ICC
                    delta_x = ((cos(delta_theta) * (prev_x - icc_x))
                               - (sin(delta_theta) * (prev_y - icc_y))
                               + icc_x - prev_x)

                    delta_y = ((sin(delta_theta) * (prev_x - icc_x))
                               + (cos(delta_theta) * (prev_y - icc_y))
                               + icc_y - prev_y)

                # update the estimated total time passed since odometry started
                self.status['pose_time_s'] = self.status['pose_time_s'] + average_delta_t_s

                # update the robot's velocity estimates
                self.status['x_vel'] = delta_travel / average_delta_t_s
                self.status['y_vel'] = 0.0
                self.status['theta_vel'] = delta_theta / average_delta_t_s

                # update the robot's pose estimates
                self.status['x'] = prev_x + delta_x
                self.status['y'] = prev_y + delta_y
                self.status['theta'] = (prev_theta + delta_theta) % (2.0 * pi)


    # ################################

    def motor_current_to_translation_force(self,il,ir):
        return self.params['force_N_per_A']*il+self.params['force_N_per_A']*ir

    def motor_current_to_rotation_torque(self,il,ir):
        r = self.params['wheel_separation_m'] / 2.0
        return (self.params['force_N_per_A']*il*r)-(self.params['force_N_per_A']*ir*r)


    def translation_force_to_motor_current(self,f_N): #Assume evenly balanced
        il=(f_N/2)/self.params['force_N_per_A']
        ir = (f_N / 2) / self.params['force_N_per_A']
        return il, ir

    def rotation_torque_to_motor_current(self,tq_Nm):
        r = self.params['wheel_separation_m'] / 2.0
        fl= tq_Nm/r/2
        fr= -1*tq_Nm/r/2
        return fl/self.params['force_N_per_A'], fr/self.params['force_N_per_A']

    def translate_to_motor_rad(self,x_m):
        circ=self.params['wheel_diameter_m']*math.pi
        return deg_to_rad(360*self.params['gr']*x_m/circ)

    def motor_rad_to_translate(self,x_r):
        circ = self.params['wheel_diameter_m'] * math.pi
        return rad_to_deg(x_r)*circ/360/self.params['gr']

    def rotate_to_motor_rad(self,x_r):
        r = self.params['wheel_separation_m'] / 2.0
        c = r * x_r #distance wheel travels (m)
        return self.translate_to_motor_rad(c)

    def motor_rad_to_rotate(self, x_r):
        c = self.motor_rad_to_translate(x_r)
        r = self.params['wheel_separation_m'] / 2.0
        ang_rad = c /r
        return ang_rad

    def translation_to_rotation(self,x_m):
        x_mr=self.translate_to_motor_rad(x_m)
        x_r=self.motor_rad_to_rotate(x_mr)
        return x_r

    def rotation_to_translation(self,x_r):
        x_mr=self.rotate_to_motor_rad(x_r)
        x_m=self.motor_rad_to_translate(x_mr)
        return x_m



