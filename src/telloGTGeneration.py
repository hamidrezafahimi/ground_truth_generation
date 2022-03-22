#!/usr/bin/env python
# import matplotlib
# matplotlib.use('Agg')

import rospy
from sensor_msgs.msg import Image
from nav_msgs.msg import Odometry
import sys
sys.path.remove('/opt/ros/kinetic/lib/python2.7/dist-packages')
from cv_bridge import CvBridge, CvBridgeError
import cv2 as cv
import numpy as np
import scipy.spatial as ssp
import matplotlib.pyplot as plt
import time
import pandas as pd
import os
import math
from pathlib import Path


ARUCO_DICT = {
	"DICT_4X4_50": cv.aruco.DICT_4X4_50,
	"DICT_4X4_100": cv.aruco.DICT_4X4_100,
	"DICT_4X4_250": cv.aruco.DICT_4X4_250,
	"DICT_4X4_1000": cv.aruco.DICT_4X4_1000,
	"DICT_5X5_50": cv.aruco.DICT_5X5_50,
	"DICT_5X5_100": cv.aruco.DICT_5X5_100,
	"DICT_5X5_250": cv.aruco.DICT_5X5_250,
	"DICT_5X5_1000": cv.aruco.DICT_5X5_1000,
	"DICT_6X6_50": cv.aruco.DICT_6X6_50,
	"DICT_6X6_100": cv.aruco.DICT_6X6_100,
	"DICT_6X6_250": cv.aruco.DICT_6X6_250,
	"DICT_6X6_1000": cv.aruco.DICT_6X6_1000,
	"DICT_7X7_50": cv.aruco.DICT_7X7_50,
	"DICT_7X7_100": cv.aruco.DICT_7X7_100,
	"DICT_7X7_250": cv.aruco.DICT_7X7_250,
	"DICT_7X7_1000": cv.aruco.DICT_7X7_1000,
	"DICT_ARUCO_ORIGINAL": cv.aruco.DICT_ARUCO_ORIGINAL
}

# idPoses = {1: (0, 0),
# 	3: (-6.8, 0),
# 	2: (-6.8, 7.1),
# 	4: (-17.3, 7.1)}

# 03 . 03 :
# idPoses = { 1:(0, 0),
# 	2:(12.7, 0.25),
# 	3:(-0.4, 14.2),
# 	4:(13, 25.4),
# 	5:(-8.9, 14.2),
# 	6:(12, 14.2),
# 	7:(0, 25.4),
# 	8:(4.5, 14.2) }

# 03 . 10 :
idPoses = { 1:(0, 0),
	2:(-10, 14),
	3:(-10, 9.5),
	4:(0, 18.5),
	5:(0, 14),
	6:(0, 9.5),
	7:(10, 18.5),
	8:(10, 14) }


class ArucoBasedDroneGroundTruthGeneration:

	def __init__(self, saveAddress, calibFile):

		self._markerPosesFileName = saveAddress + "/rawMarkerPoses.csv"
		self._newMarkerPosesFileName = saveAddress + "/cleanMarkerPoses.csv"
		self._odomPosesFileName = saveAddress + "/odomPoses.csv"
		self._markerImagesDir = saveAddress + "/markerDetectionFrames"
		#
		# if not os.path.exists(self._markerImagesDir):
		# 	os.mkdir(self._markerImagesDir)
		#
		# if os.path.exists(self._odomPosesFileName):
		# 	os.remove(self._odomPosesFileName)
		#
		# if os.path.exists(self._markerPosesFileName):
		# 	os.remove(self._markerPosesFileName)
		#
		# markerImages = Path(self._markerImagesDir).iterdir()
		# for mi in markerImages:
		# 	fileName = str(mi)
		# 	os.remove(fileName)

		aDictName = "DICT_4X4_250"
		self._arucoDict = cv.aruco.Dictionary_get(ARUCO_DICT[aDictName])
		self._arucoParams = cv.aruco.DetectorParameters_create()
		fs = cv.FileStorage(calibFile, cv.FILE_STORAGE_READ)
		self.setCameraParams(fs.getNode("camera_matrix").mat(),
			fs.getNode("distortion_coefficients").mat())
		# self.timer = rospy.Timer(rospy.Duration(1), self.plotData)
		self.defSub(1)
		self._axis3D = np.float32([ [0, 0, 0],
									[0.5, 0, 0],
									[0, 0.5, 0],
									[0, 0, 0.5]])
		self._markerLength = 0.478
		self._it = 0
		self._it_marker = 0
		self._odomBuffer = np.zeros((1,8))
		self._odomBufferSize = 200
		self._lastX = 0
		self._initialized = False
		self._initOdom = None
		self._beta = 18
		self._image = None
		# self._arucoPoses = np.zeros((1,3))
		# self._odomCorrectedPoses = np.zeros((1,3))
		self._arucoPoses =[]
		self._odomCorrectedPoses =[]
		self._posesBufferSize = 50


	def defSub(self, a=None):

		if a is not None:
			self.odom_sub = rospy.Subscriber("/tello/odom", Odometry, self.odomCallback)
			self.image_sub = rospy.Subscriber("/tello/camera/image_raw", Image,
				self.imageCallback)
			self.bridge = CvBridge()


	def odomCallback(self, data=None):

		if not data is None:
			t = data.header.stamp.to_sec()
			x = data.pose.pose.position.x
			y = data.pose.pose.position.y
			z = -data.pose.pose.position.z
			qx = data.pose.pose.orientation.x
			qy = data.pose.pose.orientation.y
			qz = data.pose.pose.orientation.z
			qw = data.pose.pose.orientation.w
			# R = ssp.transform.Rotation.from_quat([qx, qy, qz, qw])
			# euler = R.as_euler('zyx', degrees=True)
			# print('---')
			# print(euler)
			# # new_euler = [euler[0], -euler[2], euler[1]]
			# new_euler = [euler[0], euler[1], euler[2]]
			# # new_euler = euler
			# print(new_euler)
			# R_ = ssp.transform.Rotation.from_euler('zyx', new_euler,
			#  	degrees=True)
			# new_quat = R_.as_quat()
			# new_quat = [[qx, qy, qz, qw]]

			if x == self._lastX:
				# print('equal X')
				return

			self._lastX = x
			pose_orientation_t = np.array([x, y, z, qx, qy, qz, qw, t]).reshape(1,8)
			# pose_orientation_t = np.array([x, y, z, new_quat[0], new_quat[1],
				# new_quat[2], new_quat[3], t]).reshape(1,8)
			self.bufferOdom(pose_orientation_t)


	def savePoses(self, nums_marker, nums_odom, t):

		# print(nums_odom)
		if not nums_marker is None:

			df_marker = pd.DataFrame({'Xs':nums_marker[0], 'Ys':nums_marker[1],
			 	'Zs':nums_marker[2], 'Time':[t]})
			# df_marker = pd.DataFrame({'Xs':nums_marker[0][0], 'Ys':nums_marker[1][0],
			#  	'Zs':nums_marker[2][0]})

			df_marker.to_csv(self._markerPosesFileName, mode='a', index=False, header=False)

		if not nums_odom is None:

			df_odom = pd.DataFrame({'Xs':nums_odom[0], 'Ys':nums_odom[1],
				'Zs':nums_odom[2], 'Time':[t]})

			df_odom.to_csv(self._odomPosesFileName, mode='a', index=False, header=False)

		# if np.shape(self._arucoPoses)[0] < self._posesBufferSize:
		# 	# self._arucoPoses = np.append(self._arucoPoses, nums_marker, axis=0)
		# 	# self._odomCorrectedPoses = np.append(self._odomCorrectedPoses,
		# 	# 	nums_odom, axis=0)
		# else:
			# for k in range(self._posesBufferSize-1):
			# 	self._arucoPoses[k,:] = self._arucoPoses[k+1,:]
			# 	self._odomCorrectedPoses[k,:] = self._odomCorrectedPoses[k+1,:]
			#
			# self._arucoPoses[self._posesBufferSize-1,:] = nums
			# self._odomCorrectedPoses[self._posesBufferSize-1,:] = nums



	def bufferOdom(self, nums):

		if np.shape(self._odomBuffer)[0] < self._odomBufferSize:
			self._odomBuffer = np.append(self._odomBuffer, nums, axis=0)
		else:
			for k in range(self._odomBufferSize-1):
				self._odomBuffer[k,:] = self._odomBuffer[k+1,:]

			self._odomBuffer[self._odomBufferSize-1,:] = nums


	def imageCallback(self, data):

		t = data.header.stamp.to_sec()
		# print('image received! ---------------- time: ' + str(t))
		self._it += 1
		image = self.bridge.imgmsg_to_cv2(data, "bgr8")
		id, tvec, rvec = self.detect(image)
		# if rvec is not None: print('rvec', rvec*180/3.1415)
		arucoPose = self.getArucoPose(id, tvec)
		# odomPose, odomQuat = self.findCorrespondingOdom(t)
		odomPose, odomQuat = self.findCorrespondingOdom(t)
		if self._initialized:
			# correctedOdomPose = self.getCorrectedOdom(odomPose)
			correctedOdomPose = self.getCorrectedOdom(odomPose)
		else:
			correctedOdomPose = None

		cv.putText(image, "Aruco rvec: "+str(rvec), (100, 25),
			cv.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
		cv.putText(image, "Aruco Pose: "+str(arucoPose), (100, 50),
			cv.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
		cv.putText(image, "Corrected Odom Pose: "+str(correctedOdomPose),
			(100, 100), cv.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
		# cv.putText(image, "Original Odom Pose: "+str(odomPose), (100, 150),
		# 	cv.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
		cv.putText(image, "Original Odom Pose: "+str(odomPose), (100, 150),
			cv.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
		cv.imshow("Image", image)
		self._key = cv.waitKey(1)

		# ax = self._fig.add_subplot()
		# self._image = image.copy()
		self.savePoses(arucoPose, correctedOdomPose, t)
		# self._ax.imshow(image)
		# plt.draw()
		# fig, self._ax = plt.subplots()
		# self._ax.scatter(odomPose[0], odomPose[1])
		# plt.show()

		# if self._key == ord('s'):
			# cv.imwrite("fig-quat-transform-wxyz/img{}.jpg".format(self._it), image)
		if self._key == ord('a') and not self._initialized and not id is None:
			print('----init----')
			self.setInitOdoms(tvec, rvec, odomPose, odomQuat)


	def getCorrectedOdom(self, odomPose):

		if not self._initialized:
			return None#, None
		# print(odomQuat)
		# eu = ssp.transform.Rotation.from_quat(odomQuat)
		# odomEuler = eu.as_euler('xyz', degrees=False)
		# orientation = odomEuler.reshape(3,1) + self._relativeRotation
		# pose = odomPose.reshape(3,1) + self._relativePose
		# print('3--3', self._initOdom[0])
		odomDeltaPose = odomPose.reshape(3,1) - self._initOdom
		odomDeltaPose[1] = -odomDeltaPose[1]
		pose = np.matmul(self._odomToMarkerDCM, -odomDeltaPose) + self._initArucoPose
		# print('3--4', self._initOdom[0])
		return pose#, orientation


	def setInitOdoms(self, cam_wrt_aruco_pose, cam_wrt_aruco_euler,
		body_wrt_odom_pose, body_wrt_odom_quat):

		self._initOdom = body_wrt_odom_pose.reshape(3,1).copy()
		self._initArucoPose = cam_wrt_aruco_pose.copy()
		# eu = ssp.transform.Rotation.from_quat(body_wrt_odom_quat.copy())
		# body_wrt_odom_euler = eu.as_euler('xyz', degrees=False)
		# self._relativeRotation = arucoEuler - odomEuler.reshape(3,1)

		# body_wrt_aruco_pose = cam_wrt_aruco_pose.copy()

		# r1 = R.from_euler('xyz', [90+beta, 0, 0], degrees=True)
        # dcm_cam_to_body = r1.as_matrix()
		# beta = abs((np.pi/2) - abs(cam_wrt_aruco_euler[0]))
		# body_wrt_aruco_euler = cam_wrt_aruco_euler.copy()
		# body_wrt_aruco_euler[0] = 0


		# body_wrt_odom_euler = R_bo.as_euler('zyx', degrees=True)
		# print(body_wrt_odom_euler)
		# cv.waitKey()

		# correction_transform = []

		# R_bo = ssp.transform.Rotation.from_quat(body_wrt_odom_quat)
		# odom_to_body_dcm = R_bo.as_matrix()
		odom_to_body_dcm = self.make_DCM_from_quat(body_wrt_odom_quat)

		# odom_to_body_dcm = np.matmul(correction_transform, R_bo.as_matrix())

		# R_cb = ssp.transform.Rotation.from_euler('xyz', [-90-self._beta,0,0],
		#  	degrees=True)

		# R_cb = ssp.transform.Rotation.from_euler('zyx', [90,0,90-self._beta],
		#  	degrees=True)
		# body_to_cam_dcm = R_cb.as_matrix()
		body_to_cam_dcm = self.make_DCM_from_eul(np.array([90-self._beta,0,90])*3.1415/180)

		# ang = 90+self._beta
		# R_cb = ssp.transform.Rotation.from_euler('xyz', [-ang,0,0],
		#  	degrees=True)
		# body_to_cam_dcm = R_cb.as_matrix()


		# R_ca = ssp.transform.Rotation.from_rotvec(cam_wrt_aruco_euler.reshape(1,3))
		# R_ca = ssp.transform.Rotation.from_euler('xyz', cam_wrt_aruco_euler.reshape(1,3),
		# 	degrees=False)
		# cam_to_aruco_dcm = R_ca.inv().as_matrix()

		cam_to_aruco_dcm = self.make_DCM_from_eul(cam_wrt_aruco_euler).T

		# cam_to_aruco_dcm = R_ca.as_matrix()

		# rr = ssp.transform.Rotation.from_euler('xyz', body_wrt_aruco_euler.reshape(1,3)\
		# 	- body_wrt_odom_euler.copy(), degrees=False)
		# rrm = rr.as_matrix()
		# self._odomToMarkerDcm = rrm
		self._odomToMarkerDCM = np.matmul(cam_to_aruco_dcm, np.matmul(body_to_cam_dcm,
			odom_to_body_dcm))
		# self._odomToMarkerDCM = np.matmul(cam_to_aruco_dcm,	odom_to_body_dcm)
		# print('2---2', odomEuler.reshape(3,1))
		# print('2---2', arucoEuler)
		# print(self._relativeRotation)
		self._initialized = True


	def getArucoPose(self, id, pose):

		if not id is None and int(id) in idPoses.keys():
			return np.array([idPoses[int(id)][0] + pose[0], idPoses[int(id)][1]\
			 	+ pose[1], pose[2]])
		else:
			return None


	def findCorrespondingOdom(self, time):

		minDiff = 1e9
		pose = None
		orientation = None
		odomT = None
		for k in range(np.shape(self._odomBuffer)[0]):
			diff = abs(time-self._odomBuffer[k,7])
			if diff < minDiff:
				minDiff = diff
				pose = self._odomBuffer[k, :3]
				orientation = self._odomBuffer[k, 3:7]
				odomT = self._odomBuffer[k,7]
		# if not odomT is None:
		# 	print('image and odom delay:', time-odomT)
		return pose, orientation


	def isRotationMatrix(self, R):
	    Rt = np.transpose(R)
	    shouldBeIdentity = np.dot(Rt, R)
	    I = np.identity(3, dtype=R.dtype)
	    n = np.linalg.norm(I - shouldBeIdentity)
	    return n < 1e-6



	def rotationMatrixToEulerAngles(self, R):
	    assert (self.isRotationMatrix(R))

	    sy = math.sqrt(R[0, 0] * R[0, 0] + R[1, 0] * R[1, 0])

	    singular = sy < 1e-6

	    if not singular:
	        x = math.atan2(R[2, 1], R[2, 2])
	        y = math.atan2(-R[2, 0], sy)
	        z = math.atan2(R[1, 0], R[0, 0])
	    else:
	        x = math.atan2(-R[1, 2], R[1, 1])
	        y = math.atan2(-R[2, 0], sy)
	        z = 0

	    return np.array([x, y, z])



	def detect(self, img):

		R_flip  = np.zeros((3,3), dtype=np.float32)
		R_flip[0,0] = 1.0
		R_flip[1,1] =-1.0
		R_flip[2,2] =-1.0

		(corners, ids, rejected) = cv.aruco.detectMarkers(img, self._arucoDict,
			parameters=self._arucoParams)

		# if not self.drawMarkers(img, corners, ids):
		# 	cv.imshow("Image", img)
		# 	cv.waitKey(30)
		# 	return

		if ids is not None:
			Cs = []
			Is = []
			for k,i in enumerate(ids):
				if int(i) in idPoses.keys():
					Is.append(i)
					Cs.append(corners[k])

			self.drawMarkers(img, np.array(Cs), np.array(Is))

			# if len(Is) == 1:
			if bool(Is):
				self._it_marker += 1
				# rvec, tvec, _ = cv.aruco.estimatePoseSingleMarkers(Cs,
				# 	self._markerLength, self._cameraMatrix, self._distortionMatrix)

				# Rt, _ = cv.Rodrigues(rvec)
				# camR = np.transpose(Rt)
				# camRvec, _ = cv.Rodrigues(camR)
				# # print(camR, tvec)
				# camTvec = np.matmul(-camR, tvec.reshape(3,1))
				# cv.aruco.drawAxis(img,  self._cameraMatrix, self._distortionMatrix,
				# 	rvec, tvec, 0.5)

				ret = cv.aruco.estimatePoseSingleMarkers(Cs[0], self._markerLength, self._cameraMatrix, self._distortionMatrix)

		        #-- Unpack the output, get only the first
				rvec, tvec = ret[0][0,0,:], ret[1][0,0,:]

				#-- Draw the detected marker and put a reference frame over it
				# cv.aruco.drawDetectedMarkers(img, Cs)
				cv.aruco.drawAxis(img, self._cameraMatrix, self._distortionMatrix,
				 	rvec, tvec, 0.5)
				cv.imwrite(self._markerImagesDir+"/img{}.jpg".format(self._it_marker),
					img)
				#-- Obtain the rotation matrix tag->camera
				R_ct    = np.matrix(cv.Rodrigues(rvec)[0])
				R_tc    = R_ct.T
				self._R_tc = R_tc

				#-- Now get Position and attitude f the camera respect to the marker
				pos_camera = -R_tc*np.matrix(tvec).T
				#-- Get the attitude of the camera respect to the frame
				roll_camera, pitch_camera, yaw_camera = self.rotationMatrixToEulerAngles(R_flip*R_tc)

				return Is[0], np.array(pos_camera), np.array([roll_camera, pitch_camera, yaw_camera])
				# return Is[0], camTvec, camRvec
		return None, None, None


	def deleteOutliers(self):

		df = pd.read_csv(self._markerPosesFileName, sep=',', header=None)
		# markerImages = sorted(os.listdir('../markerDetectionFrames'))
		markerImages = sorted(Path(self._markerImagesDir).iterdir(), key=os.path.getmtime)
		num = len(markerImages)
		toBeRemoved = []
		for k, mi in enumerate(markerImages):
			fileName = str(mi)
			print(fileName)
			print(os.path.isfile(fileName))
			img = cv.imread(fileName)
			cv.imshow("marker image", img)
			key = cv.waitKey()

			if key == ord('q'):
				cv.destroyWindow("marker image")
				break

			elif key == ord('d'):
				toBeRemoved.append(k)
				# os.remove(fileName)

		print(toBeRemoved)
		# df.drop(toBeRemoved, axis=0)
		df.to_csv(self._newMarkerPosesFileName, index=False, header=False)
		print("Deleting Outliers Done!")
			# translationVector = self.findRealTranslationVec(tvec, rvec)

			# axis2D, j = cv.projectPoints(self._axis3D, rvec, tvec, self._cameraMatrix,
			# 	self._distortionMatrix)
			#
			# cv.line(img, (axis2D[0][0][0], axis2D[0][0][1]), (axis2D[1][0][0],axis2D[1][0][1]), (255,255,0), 2)
			# cv.line(img, (axis2D[0][0][0], axis2D[0][0][1]), (axis2D[2][0][0],axis2D[2][0][1]), (255,0,255), 2)
			# cv.line(img, (axis2D[0][0][0], axis2D[0][0][1]), (axis2D[3][0][0],axis2D[3][0][1]), (0,255,255), 2)


	# def findRealTranslationVec(self, tvecs, rvecs):
	#
	#     R = cv.Rodrigues(rvecs.reshape(3,1))[0]
	#     cameraTranslationVector = np.dot(-R.transpose(), tvecs.reshape(3,1))
	#     return cameraTranslationVector


	def drawMarkers(self, image, corners, ids):

		if len(corners) > 0:
			# flatten the ArUco IDs list
			ids = ids.flatten()

			# includes = False
			# for id in ids:
			# 	if id in IDs:
			# 		includes = True
			# if not includes:
			# 	return False

			# loop over the detected ArUCo corners
			for (markerCorner, markerID) in zip(corners, ids):
				# extract the marker corners (which are always returned in
				# top-left, top-right, bottom-right, and bottom-left order)
				# if not markerID in IDs:
				# 	continue
				corners = markerCorner.reshape((4, 2))
				(topLeft, topRight, bottomRight, bottomLeft) = corners
				# convert each of the (x, y)-coordinate pairs to integers
				topRight = (int(topRight[0]), int(topRight[1]))
				bottomRight = (int(bottomRight[0]), int(bottomRight[1]))
				bottomLeft = (int(bottomLeft[0]), int(bottomLeft[1]))
				topLeft = (int(topLeft[0]), int(topLeft[1]))
				# draw the bounding box of the ArUCo detection
				cv.line(image, topLeft, topRight, (0, 255, 0), 2)
				cv.line(image, topRight, bottomRight, (0, 255, 0), 2)
				cv.line(image, bottomRight, bottomLeft, (0, 255, 0), 2)
				cv.line(image, bottomLeft, topLeft, (0, 255, 0), 2)
				# compute and draw the center (x, y)-coordinates of the ArUco
				# marker
				cX = int((topLeft[0] + bottomRight[0]) / 2.0)
				cY = int((topLeft[1] + bottomRight[1]) / 2.0)
				cv.circle(image, (cX, cY), 4, (0, 0, 255), -1)
				# draw the ArUco marker ID on the image
				cv.putText(image, str(markerID),
					(topLeft[0], topLeft[1] - 15), cv.FONT_HERSHEY_SIMPLEX,
					0.5, (0, 255, 0), 2)
				# print("[INFO] ArUco marker ID: {}".format(markerID))

			# return True


	def setCameraParams(self, cameraMatrix, distortionMatrix):
		self._cameraMatrix = cameraMatrix
		self._distortionMatrix = distortionMatrix

	def make_DCM_from_quat(self, quat):

		q0 = quat[3]
		q1 = quat[0]
		q2 = quat[1]
		q3 = quat[2]

		DCM = np.zeros((3,3))
		DCM[0,0] = q0**2+q1**2-q2**2-q3**2
		DCM[0,1] = 2*(q1*q2+q0*q3)
		DCM[0,2] = 2*(q1*q3-q0*q2)
		DCM[1,0] = 2*(q1*q2-q0*q3)
		DCM[1,1] = q0**2-q1**2+q2**2-q3**2
		DCM[1,2] = 2*(q2*q3+q0*q1)
		DCM[2,0] = 2*(q1*q3+q0*q2)
		DCM[2,1] = 2*(q2*q3-q0*q1)
		DCM[2,2] = q0**2-q1**2-q2**2+q3**2

		return DCM

	def make_DCM_from_eul(self, eul):

		phi = eul[0]
		theta = eul[1]
		psi = eul[2]

		DCM = np.zeros((3,3))
		DCM[0,0] = np.cos(psi)*np.cos(theta)
		DCM[0,1] = np.sin(psi)*np.cos(theta)
		DCM[0,2] = -np.sin(theta)
		DCM[1,0] = np.cos(psi)*np.sin(theta)*np.sin(phi)-np.sin(psi)*np.cos(phi)
		DCM[1,1] = np.sin(psi)*np.sin(theta)*np.sin(phi)+np.cos(psi)*np.cos(phi)
		DCM[1,2] = np.cos(theta)*np.sin(phi)
		DCM[2,0] = np.cos(psi)*np.sin(theta)*np.cos(phi)+np.sin(psi)*np.sin(phi)
		DCM[2,1] = np.sin(psi)*np.sin(theta)*np.cos(phi)-np.cos(psi)*np.sin(phi)
		DCM[2,2] = np.cos(theta)*np.cos(phi)

		return DCM



rospy.init_node('telloGTGeneration', anonymous=True)

agtg = ArucoBasedDroneGroundTruthGeneration(\
	"/media/hamidreza/Local Disk/rosbag/93/tello_test/2022-03-10/16-33-13",
	"../params/telloCam.yaml")
agtg.deleteOutliers()

rospy.spin()