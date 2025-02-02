from imutils.video import VideoStream
from imutils.video import FPS
import imutils
import cv2,os,urllib.request,pickle
from matplotlib import image
import numpy as np
from django.conf import settings 
from transfer import extract_embeddings
from transfer import train_model
# load our serialized face detector model from disk
protoPath = os.path.join(settings.BASE_DIR, "face_detection_model\\deploy.prototxt")
print(protoPath)
modelPath = os.path.join(settings.BASE_DIR,"face_detection_model\\res10_300x300_ssd_iter_140000.caffemodel")
detector = cv2.dnn.readNetFromCaffe(protoPath, modelPath)
# load our serialized face embedding model from disk
embedder = cv2.dnn.readNetFromTorch(os.path.join(settings.BASE_DIR,'face_detection_model/openface_nn4.small2.v1.t7'))
# load the actual face recognition model along with the label encoder
recognizer = os.path.join(settings.BASE_DIR, "output\\recognizer.pickle")
recognizer = pickle.loads(open(recognizer, "rb").read())
le = os.path.join(settings.BASE_DIR, "output\\le.pickle")
le = pickle.loads(open(le, "rb").read())
dataset = os.path.join(settings.BASE_DIR, "dataset")
user_list = [ f.name for f in os.scandir(dataset) if f.is_dir() ]

class FaceDetect(object):
	def __init__(self):
		extract_embeddings.embeddings()
		train_model.model_train()
		# initialize the video stream, then allow the camera sensor to warm up
		self.vs = VideoStream(src=0).start()
		# start the FPS throughput estimator
		self.fps = FPS().start()

	def __del__(self):
		cv2.destroyAllWindows()

	def get_frame(self):
		# grab the frame from the threaded video stream
		frame = self.vs.read()
		frame = cv2.flip(frame,1)

		# resize the frame to have a width of 600 pixels (while
		# maintaining the aspect ratio), and then grab the image
		# dimensions
		frame = imutils.resize(frame, width=600)
		(h, w) = frame.shape[:2]

		# construct a blob from the image
		imageBlob = cv2.dnn.blobFromImage(
			cv2.resize(frame, (300, 300)), 1.0, (300, 300),
			(104.0, 177.0, 123.0), swapRB=False, crop=False)

		# apply OpenCV's deep learning-based face detector to localize
		# faces in the input image
		detector.setInput(imageBlob)
		detections = detector.forward()

		sketch_image_list = []
		canny_image_list = []
		enhanced_image_list = []
		point_list = []


		# loop over the detections
		for i in range(0, detections.shape[2]):
			# extract the confidence (i.e., probability) associated with
			# the prediction
			confidence = detections[0, 0, i, 2]

			# filter out weak detections
			if confidence > 0.5:
				# compute the (x, y)-coordinates of the bounding box for
				# the face
				box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
				(startX, startY, endX, endY) = box.astype("int")

				# extract the face ROI
				face = frame[startY:endY, startX:endX]
				(fH, fW) = face.shape[:2]

				# ensure the face width and height are sufficiently large
				if fW < 20 or fH < 20:
					continue

				# construct a blob for the face ROI, then pass the blob
				# through our face embedding model to obtain the 128-d
				# quantification of the face
				faceBlob = cv2.dnn.blobFromImage(face, 1.0 / 255,
					(96, 96), (0, 0, 0), swapRB=True, crop=False)
				embedder.setInput(faceBlob)
				vec = embedder.forward()

				# perform classification to recognize the face
				preds = recognizer.predict_proba(vec)[0]
				j = np.argmax(preds)
				proba = preds[j]
				name = le.classes_[j]


				# draw the bounding box of the face along with the
				# associated probability
				text = "{}: {:.2f}%".format(name, proba * 100)
				y = startY - 10 if startY - 10 > 10 else startY + 10

				
				cropped = frame[startY:endY, startX: endX].copy()
				gray_image = cv2.cvtColor(cropped,cv2.COLOR_BGR2GRAY)
				
				## 스케치 스타일
				inverted_gray_image = 255 - gray_image
				blurred_img = cv2.GaussianBlur(inverted_gray_image,(21,21),0)
				inverted_blurred_img = 255 - blurred_img
				pencil_sketch_face = cv2.divide(gray_image,inverted_blurred_img,scale=256.0)
				

				## 캐니 에지 부분
				# 픽셀 강도의 중간값을 계산
				median_intensity = np.median(gray_image)
				# 중간 픽셀 강도에서 위아래 1 표준편차 떨어진 값을 임곗값으로 지정
				lower_threshold = int(max(0, (1.0 - 0.33) * median_intensity))
				upper_threshold = int(min(255, (1.0 + 0.33) * median_intensity))
				# Canny edge detection 적용
				image_canny = cv2.Canny(gray_image, lower_threshold, upper_threshold)

				

				sketch_image_list.append(cv2.cvtColor(pencil_sketch_face,cv2.COLOR_GRAY2RGB))
				canny_image_list.append(cv2.cvtColor(image_canny,cv2.COLOR_GRAY2RGB))
				enhanced_image_list.append(cv2.cvtColor(cv2.equalizeHist(gray_image),cv2.COLOR_GRAY2RGB))
				point_list.append((startY,endY, startX,endX))




				# cv2.rectangle(frame, (startX, startY), (endX, endY),
				# 	(0, 0, 255), 2)
		
				# cv2.putText(frame, text, (startX, y),
				# 	cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 2)

		sketch_image = frame.copy()
		canny_image = frame.copy()
		enhanced_image = frame.copy()

		for img,point in zip(sketch_image_list,point_list):
			sketch_image[point[0]:point[1],point[2]:point[3]] = img

		for img,point in zip(canny_image_list,point_list):
			canny_image[point[0]:point[1],point[2]:point[3]] = img

		for img,point in zip(enhanced_image_list,point_list):
			enhanced_image[point[0]:point[1],point[2]:point[3]] = img


		frame = cv2.hconcat([frame,sketch_image])
		canny_image = cv2.hconcat([canny_image,enhanced_image])

		frame = cv2.vconcat([frame,canny_image])



		# update the FPS counter
		self.fps.update()
		ret, jpeg = cv2.imencode('.jpg', frame)
		return jpeg.tobytes()
		