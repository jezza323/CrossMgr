import numpy as np
import cv2
from datetime import datetime, timedelta
import time
from collections import deque
from Queue import Empty
from multiprocessing import Process, Pipe, Queue
from threading import Thread, Timer
from FrameCircBuf import FrameCircBuf

now = datetime.now

def getVideoCapture( usb=1, fps=30, width=640, height=480 ):
	cap = cv2.VideoCapture( usb )
	cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
	cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
	cap.set(cv2.CAP_PROP_FPS, fps)
	return cap

class VideoCaptureManager( object ):
	def __init__( self, **kwargs ):
		self.cap = getVideoCapture(**kwargs)
	def __enter__(self):
		return self.cap
	def __exit__(self, type, value, traceback):
		self.cap.release()

def CamServer( qIn, pWriter, camInfo=None ):
	sendUpdates = {}
	tsSeen = set()
	camInfo = camInfo or {}
	bufferSeconds = 8
	backlog = deque()
	
	while 1:
		with VideoCaptureManager(**camInfo) as cap:
			time.sleep( 0.25 )
			frameCount = 0
			tsSeen.clear()
			fcb = FrameCircBuf( int(camInfo.get('fps', 30) * bufferSeconds) )
			tsQuery = tsMax = now()
			
			while 1:
				# Capture frame-by-frame
				try:
					ret, frame = cap.read()
				except KeyboardInterrupt:
					return
				
				ts = now()
				if not ret:
					break
				fcb.append( ts, frame )
				
				try:
					m = qIn.get_nowait()
					while 1:
						cmd = m['cmd']
						if cmd == 'query':
							if m['tStart'] > ts:
								# Reschedule future requests for later.
								Timer( (m['tStart'] - ts).total_seconds(), qIn.put, m ).start()
								continue
							
							if (ts - tsQuery).total_seconds() > bufferSeconds or len(tsSeen) > 5000:
								tsSeen.clear()
							tsQuery = ts

							times, frames = fcb.getTimeFrames( m['tStart'], m['tEnd'], tsSeen )
							backlog.extend( (t, f) for t, f in zip(times, frames) )
							
							if m['tEnd'] > tsMax:
								tsMax = m['tEnd']
						elif cmd == 'send_update':
							sendUpdates[m['name']] = m['freq']
						elif cmd == 'cancel_update':
							if 'name' not in m:
								sendUpdates.clear()
							else:
								sendUpdates.pop(m['name'], None)
						elif cmd == 'cam_info':
							camInfo = m['info'] or {}
							break
						elif cmd == 'terminate':
							pWriter.send( {'cmd':'terminate'} )
							return
						else:
							assert False, 'Unknown Command'
						m = qIn.get_nowait()						
				except Empty:
					pass
				
				if tsMax > ts:
					backlog.append( (ts, frame) )
					tsSeen.add( ts )

				# Slow updates if we have a backlog.
				for name, f in sendUpdates.iteritems():
					if frameCount % (11 if backlog else f) == 0:
						pWriter.send( {'cmd':'update', 'name':name, 'frame':frame } )
				
				# Don't send too many frames so as not to do too much processing and lose frames.
				if backlog:
					pWriter.send( { 'cmd':'response', 'ts_frames': [backlog.popleft() for i in xrange(min(4, len(backlog)))] } )
						
				frameCount += 1
				
def getCamServer( camInfo=None ):
	qIn = Queue()
	pReader, pWriter = Pipe( False )
	p = Process( target=CamServer, args=(qIn, pWriter, camInfo), name='CamServer' )
	p.daemon = True
	p.start()
	return qIn, pReader
	
def callCamServer( qIn, cmd, **kwargs ):
	kwargs['cmd'] = cmd
	qIn.put( kwargs )
	
if __name__ == '__main__':
	def handleMessages( q ):
		while 1:
			m = q.get()
			print ', '.join( '{}={}'.format(k, v if k not in ('frame', 'ts_frames') else len(v)) for k, v in m.iteritems())
	
	qIn, pWriter = getCamServer( dict(usb=1, width=1920, height=1080, fps=30) )
	thread = Thread( target=handleMessages, args=(pWriter,) )
	thread.daemon = True
	thread.start()
	
	time.sleep( 2.0 )
	callCamServer( qIn, 'cam_info', info=dict(usb=1, width=1920, height=1080, fps=30) )
	time.sleep( 5.0 )
	#callCamServer( qIn, 'send_update', name='a', freq=4 )
	#callCamServer( qIn, 'send_update', name='b', freq=1 )
	time.sleep( 3 )
	#callCamServer( qIn, 'cancel_update', name='a' )
	#callCamServer( qIn, 'cancel_update', name='b' )
	callCamServer( qIn, 'query', tStart=now()-timedelta(seconds=1), tEnd=now() )
	time.sleep( 2 )
	callCamServer( qIn, 'query', tStart=now()-timedelta(seconds=1), tEnd=now() )
	time.sleep( 2 )
	callCamServer( qIn, 'query', tStart=now()-timedelta(seconds=1), tEnd=now() )
	time.sleep( 2 )
	callCamServer( qIn, 'query', tStart=now()-timedelta(seconds=1), tEnd=now() )
	time.sleep( 2 )
	callCamServer( qIn, 'terminate' )
	