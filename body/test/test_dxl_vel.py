import stretch_body.robot_params
import unittest
from stretch_body import dynamixel_hello_XL430
import time


class TestDynamixelVelocity(unittest.TestCase):
    """
    This script tests the accuracy of velocity control interface for Dynamixel servos
    The test is designed to rotate the wrist_yaw joint at a constant velocity for given period time
    and is expected to cover the distance==velocity*time.
    This tests the higher level DynamixelHelloXL430()->set_velocity() and the lower level DynamixelXL430()->set_vel()
    """
    
    @classmethod
    def setUpClass(self):
        self.dynamixel = dynamixel_hello_XL430.DynamixelHelloXL430('wrist_yaw')
        self.dynamixel.startup()
        if not self.dynamixel.is_calibrated:
            self.dynamixel.home()
        while self.dynamixel.is_homing:
            time.sleep(0.1)
            
    @classmethod
    def tearDownClass(self):
        self.dynamixel.stop()
    
    def velocity_control_test(self, set_vel_method):
        
        print("\n\nStarting Constant Velocity Control...")
        print(f"Vel Limit: {self.dynamixel.motor.get_vel_limit()} ticks/s")
        
        # rotate 90deg in 5s i.e. 1.57 rad == vel*total_time
        vel = 0.314 #rad 
        total_time = 5 #s

        self.dynamixel.pull_status()
        start_pos = self.dynamixel.status['pos']
        print(f"Start pos: {start_pos} rad")
        start = time.time()
        while time.time()-start < total_time:
            v_Des = self.dynamixel.world_rad_to_ticks_per_sec(vel)
            if set_vel_method=="DynamixelHelloXL430":
                self.dynamixel.set_velocity(vel) 
            if set_vel_method=="DynamixelXL430":
                self.dynamixel.motor.set_vel(v_Des)
            self.dynamixel.pull_status()
            # print(f"Target Vel: {vel} rad/s | Target V_Des: {v_Des} ticks/s | Monitor Vel_ticks: {self.dynamixel.status['vel_ticks']} rad/s")
            time.sleep(0.05)
            
        self.dynamixel.pull_status()
        end_pos = self.dynamixel.status['pos']

        print(f"End pos: {end_pos} rad")
        print(f"\nTotal Rotation: {abs(start_pos-end_pos)} rad | Expected: {vel*total_time} rad")
        print(f"Avg Velocity: {abs(end_pos-start_pos)/total_time} rad/s | Expected: {vel} rad/s\n")
        
        self.assertAlmostEqual(abs(start_pos-end_pos),vel*total_time, 1)
        self.assertAlmostEqual(abs(end_pos-start_pos)/total_time, vel, 1)
        
    
    def test_DynamixelHelloXL430_set_velocity(self):
        """
        Test the Higher level DynamixelHelloXL430()->set_velocity()
        """
        self.velocity_control_test(set_vel_method="DynamixelHelloXL430")
    
    def test_DynamixelXL430_set_vel(self):
        """
        Test the Lower level DynamixelXL430()->set_vel()
        """
        self.dynamixel.motor.disable_torque()
        self.dynamixel.motor.enable_vel()
        self.dynamixel.motor.enable_torque()
        self.velocity_control_test(set_vel_method="DynamixelXL430")