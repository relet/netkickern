#!/usr/bin/env python

print """
  netkickern - Copyright (C) 2008 Thomas Hirsch
  This program comes with ABSOLUTELY NO WARRANTY;
  This is free software, and you are welcome to redistribute it under the
  conditions of the GNU General Public Licence version 3 (GPLv3)
  see: http://www.gnu.org/licenses/gpl-3.0.html
"""

DATAPATH="./data/" # where to find data files (.x models)
PORT=5036          # default port to use for connections

STEPS = 10         #each mouse movement is divided into STEPS steps, to keep physics changes smooth. 10 is good for solo use

P1NAME = "NET"     #the server, currently.
P2NAME = "MOTION"  #the client, currently.

#list of used packet types
PACKET_HELLO = 0   # identification using magic word
PACKET_SCORE = 1   # send a score update to client
PACKET_PING  = 2   # measure round trip time
PACKET_PONG  = 3   # measure round trip time
PACKET_START = 4   # start game notification
PACKET_MOVE  = 5   # movement update client -> server
PACKET_SET   = 6   # physics & movement update, server -> client

MAGIC_WORD   = "kickern?"
PROTOCOL_VERSION = 2  # to be increased with each protocol change

ROLE_SERVER  = 1
ROLE_CLIENT  = 2

### IMPORTS ###########################################################

import ode
import sys
import time

from random import random
from math import sin, cos, pi, atan2, sqrt

from pandac.PandaModules import *
from direct.distributed.PyDatagram import PyDatagram 
from direct.distributed.PyDatagramIterator import PyDatagramIterator 
#more imports after network setup!

### Define network role ###############################################
def startGame():
  taskMgr.add(moveKickerTask, "gameTask");
  if role==ROLE_SERVER:
    taskMgr.add(pingTask, "pingTask"); # not needed, currently. enable to determine rtt (deltatime)
   
def tskReaderPolling(taskdata):
  while cReader.dataAvailable():
    datagram=NetDatagram()  # catch the incoming data in this instance
    # Check the return value; if we were threaded, someone else could have
    # snagged this data before we did
    if cReader.getData(datagram):
      myProcessDataFunction(datagram) 
  return Task.cont

def pingTask(task):
  if (task.frame % 1000) > 0: #determine network delay every now and then (every 1000 frames)
    return Task.cont
  ping = PyDatagram()
  ping.addUint16(PACKET_PING)
  ping.addFloat64(time.time())
  cWriter.send(ping, myConnection)
  return Task.cont

def myProcessDataFunction(datagram):
  data = PyDatagramIterator(datagram)
  try: 
    pktType = data.getUint16()
    if pktType==PACKET_SET:
      setGameStatus(data)
    elif pktType==PACKET_SCORE:
      setScore(data)
    elif pktType==PACKET_MOVE:
      setOpponentMove(data)
    elif pktType==PACKET_HELLO:
      magic = data.getString()
      proto = data.getUint16()
      if magic != MAGIC_WORD:
        print "Connecting party did not identify as netkickern client."
        sys.exit(1)
      if proto != PROTOCOL_VERSION:
        print "Connecting party used incompatible protocol version "+str(proto)+"."
        print "We are using "+str(PROTOCOL_VERSION)+"."
        sys.exit(1)
      print "Ok, client connected."
      welcome = PyDatagram()
      welcome.addUint16(PACKET_START)
      cWriter.send(welcome, myConnection)
      startGame()
    elif pktType==PACKET_START:
      print "connection to game host confirmed."
      startGame()
    elif pktType==PACKET_PING:
      stime = data.getFloat64()
      pong = PyDatagram()
      pong.addUint16(PACKET_PONG)
      pong.addFloat64(stime)
      cWriter.send(pong, myConnection)
    elif pktType==PACKET_PONG:
      stime = data.getFloat64()
      now = time.time()
      deltatime = now-stime   # TODO: use this to delay mouse movements by deltatime/2
      print "network delay: "+str(deltatime*500)+"ms " #rtt/2
  except Exception, e:
    print e 
    sys.exit(1) #wow, this is what I call exception handling.. 
  return

role = ROLE_SERVER #strings are bulky but quick and readable.
if len(sys.argv)>1:
  role   = ROLE_CLIENT
  server = sys.argv[1]
  print    server

cManager = QueuedConnectionManager()
cReader  = QueuedConnectionReader(cManager, 0)
cWriter  = ConnectionWriter(cManager,0)

if role == ROLE_SERVER:
  cListener = QueuedConnectionListener(cManager, 0)
  activeConnections=[] # We'll want to keep track of these later
  tcpSocket = cManager.openTCPServerRendezvous(PORT,1000)
  cListener.addConnection(tcpSocket)

  print "================================"
  print "waiting for opponent to connect."
  print "================================"
  try:
    while not cListener.newConnectionAvailable():
      time.sleep(0.1)
  except KeyboardInterrupt:
    print "aborted."
    #sys.exit(1)

  rendezvous = PointerToConnection()
  netAddress = NetAddress()
  myConnection = PointerToConnection()

  if cListener.getNewConnection(rendezvous,netAddress,myConnection):
    myConnection = myConnection.p()
    activeConnections.append(myConnection) # Remember connection
    cReader.addConnection(myConnection)    # Begin reading connection

else: 
  myConnection=cManager.openTCPClientConnection(server,PORT,3000)
  if myConnection:
    cReader.addConnection(myConnection)    # receive messages from server
    welcome = PyDatagram()
    welcome.addUint16(PACKET_HELLO)
    welcome.addString(MAGIC_WORD)          # the magic word to initiate a game.
    welcome.addUint16(PROTOCOL_VERSION) 
    cWriter.send(welcome, myConnection)

if not myConnection:
  print "connection failed."
  sys.exit(1)

### Post-networking imports ############################################
# (to prevent Panda3D from opening windows before network setup ########
import direct.directbase.DirectStart
from direct.task import Task

font = loader.loadFont(DATAPATH+"fonts/mainfram.egg")

def textFormat(text):
  text.setFont(font)
  text.setTextColor(1,1,1,1)
  text.setShadow(.05,.05)
  text.setShadowColor(0,0,0,1)

title = TextNode('testtext')
title.setText("NetKickern")
title.setAlign(TextNode.ACenter)
textFormat(title)
textNodePath = aspect2d.attachNewNode(title)
textNodePath.setScale(0.10)
textNodePath.setPos(VBase3(0,0,.88))

p1score = 0
score1 = TextNode('t1score')
score1.setText(P1NAME+" 0")
textFormat(score1)
textNodePath1 = aspect2d.attachNewNode(score1)
textNodePath1.setScale(0.10)

p2score = 0
score2 = TextNode('t2score')
score2.setText(P2NAME+" 0")
textFormat(score2)
textNodePath2 = aspect2d.attachNewNode(score2)
textNodePath2.setScale(0.10)

if role==ROLE_SERVER:
  score1.setAlign(TextNode.ALeft)
  textNodePath1.setPos(VBase3(-1,0,.75))
  score2.setAlign(TextNode.ARight)
  textNodePath2.setPos(VBase3(1,0,.75))
else:
  score1.setAlign(TextNode.ARight)
  textNodePath1.setPos(VBase3(1,0,.75))
  score2.setAlign(TextNode.ALeft)
  textNodePath2.setPos(VBase3(-1,0,.75))

base.setFrameRateMeter(True)
taskMgr.add(tskReaderPolling,"Poll the connection reader",-40)


### Setup pyODE ########################################################
world = ode.World()
space = ode.Space()
contactgroup = ode.JointGroup()

world.setGravity((0,9.81,0))

## define ball
ballBody = ode.Body(world)
ballMass = ode.Mass()
ballMass.setSphere(250,0.8)
ballBody.setMass(ballMass)
ballGeom = ode.GeomSphere(space, radius=0.8)
ballGeom.setBody(ballBody)
# place ball
ballBody.setPosition((-3,60,0))

## define table
#tableGeom = ode.GeomBox(space, (28,8,8)) #theoretical extents
tableGeom = ode.GeomBox(space, (56,1,32)) #trial and error

baseheight = 82.4

#tableGeom.setPosition((0,85.7,0))        #theory
tableGeom.setPosition((0,baseheight,0))   #trial and error

#side walls
wallGeom = []
wallGeom.append( ode.GeomBox(space, (56,10,2)) )
wallGeom[0].setPosition((0,baseheight-5,15.8))
wallGeom.append( ode.GeomBox(space, (56,10,2)) )
wallGeom[1].setPosition((0,baseheight-5,-15.8))

#goalside walls
wallGeom.append( ode.GeomBox(space, (2,5,9)) )
wallGeom[2].setPosition((-28,baseheight-2.5,-9))
wallGeom.append( ode.GeomBox(space, (2,5,9)) )
wallGeom[3].setPosition((-28,baseheight-2.5,9))
wallGeom.append( ode.GeomBox(space, (2,5,32)) )
wallGeom[4].setPosition((-28,baseheight-7.5,0))

wallGeom.append( ode.GeomBox(space, (2,5,9)) )
wallGeom[5].setPosition((28,baseheight-2.5,-9))
wallGeom.append( ode.GeomBox(space, (2,5,9)) )
wallGeom[6].setPosition((28,baseheight-2.5,9))
wallGeom.append( ode.GeomBox(space, (2,5,32)) )
wallGeom[7].setPosition((28,baseheight-7.5,0))

## define kickers
kickerGeom = []
KV = 79 #"const" vertical height of kickers
for i in range(11):
  kickerGeom.append(ode.GeomBox(space,(2*0.65,6.36*0.65,2.0*0.65))) # exxagerated y height to [-3,18,3,18], actually should be [1.14, -3.18]
                                                                    # y position still has to be off-centered
  kickerGeom[i].setPosition((10,KV,10)) #just some random position. should be reassigned by mouse movement asap.

kickerGeom2 = []
for i in range(11):
  kickerGeom2.append(ode.GeomBox(space,(2*0.65,6.36*0.65,2.0*0.65))) #exxagerated y height to [-3,18,3,18], actually should be [1.14, -3.18]
                                                                     # y position still has to be off-centered
  kickerGeom2[i].setPosition((10,KV,10)) #just some random position. should be reassigned by mouse movement asap.

def near_callback(args, geom1, geom2):
  contacts=ode.collide(geom1, geom2)
  world, contactgroup = args
  for c in contacts:
    if (geom1 in kickerGeom) or (geom2 in kickerGeom) or (geom1 in kickerGeom2) or (geom2 in kickerGeom2):
      c.setMu(5E6)   #kickers have high friction, minimal bounce - FIXME: does not work. you still can't stop balls
      c.setBounce(1) 
    elif (geom1 == tableGeom) or (geom2 == tableGeom): 
      c.setMu(10)    #table has little bounce, noticeable friction
      c.setBounce(1.5) 
    elif (geom1 in wallGeom) or (geom2 in wallGeom):
      c.setMu(1)      #walls have ok bounce, noticeable friction
      c.setBounce(3)
    else:             #ignore anything else. I have no idea what that could be
      print "something undetected collided with my balls. ouch."
      continue 
    j=ode.ContactJoint(world, contactgroup, c)
    j.attach(geom1.getBody(), geom2.getBody())

### place CAMERA ######################################################
#default camera: top view

#base.camera.setHpr(0,25,0) #25deg angle sideways
#base.camera.setPos(0,0,-35)

base.camera.setHpr(0,45,0) #45deg angle sideways
base.camera.setPos(0,20,-60)

#base.camera.setHpr(0,45,0) #45deg angle sideways, zoomed
#base.camera.setPos(0,60,-20)

#base.camera.setHpr(90,0,-90) #front view, through goal
#base.camera.setPos(40,80,0)

### place LIGHTS ######################################################
#default: no shading, full colours

#TODO: add some ambient lighting
#nice to have: four spotlights and appropriate shadows, stadium style.

#not directional, but a lit ball somewhere above the stage
sun  = PointLight('sun')
sunp = render.attachNewNode(sun)
sunp.setPos(20,25,10)
render.setLight(sunp)

### LOAD and place MODELS #############################################

kicker  = loader.loadModel(DATAPATH+"models/kicker.x")
kicker2 = loader.loadModel(DATAPATH+"models/kicker.x") #FIXME: this could just as well be an instance

handle  = loader.loadModel(DATAPATH+"models/handle.x")
blocker = loader.loadModel(DATAPATH+"models/blocker.x")
handle.setPos(0,80,0)
handle.setScale(1,1,.7)
blocker.setPos(0,80,0)
blocker.setScale(.8,.8,1)

kicker.setScale(.65,.65,.65)
kicker.setPos(0,79.5,0)

kicker2.setScale(.65,.65,.65)
kicker2.setPos(0,79.5,0)

table = loader.loadModel(DATAPATH+"models/table.x")
table.reparentTo(render)
table.setScale(4,4,4)
table.setPos(0,82,0)
table.setP(90)
table.setH(180)

ball = loader.loadModel(DATAPATH+"models/ball.x")
ball.reparentTo(render)
ball.setScale(.8,.8,.8)
ball.setPos(0,70,15)

row1 = render.attachNewNode("row1") #own rows
row2 = render.attachNewNode("row2")
row3 = render.attachNewNode("row3")
row4 = render.attachNewNode("row4")

rrow1 = render.attachNewNode("rrow1") #opponent rows
rrow2 = render.attachNewNode("rdrow2")
rrow3 = render.attachNewNode("rdrow3")
rrow4 = render.attachNewNode("rrow4")

kickstance = row1.attachNewNode("k1")
kickstance.setPos(-23,0,0)
kicker.instanceTo(kickstance)
handle1 = row1.attachNewNode("h1")
handle1.setPos(-23,0,0)
handle.instanceTo(handle1)
block11 = row1.attachNewNode("b1")
block11.setPos(-23,0,5.7)
blocker.instanceTo(block11)
block12 = row1.attachNewNode("b2")
block12.setPos(-23,0,-5.7)
blocker.instanceTo(block12)

for i in range(2):
  kickstance = row2.attachNewNode("k2")
  kickstance.setPos(-16.33,0,i*12-6)
  kicker.instanceTo(kickstance)
handle2 = row2.attachNewNode("h2")
handle2.setPos(-16.33,0,0)
handle.instanceTo(handle2)

for i in range(5):
  kickstance = row3.attachNewNode("k3")
  kickstance.setPos(-4,0,i*5.5-11)
  kicker.instanceTo(kickstance)
handle3 = row3.attachNewNode("h2")
handle3.setPos(-4,0,0)
handle.instanceTo(handle3)

for i in range(3):
  kickstance = row4.attachNewNode("k4")
  kickstance.setPos(10.33,0,i*8-8)
  kicker.instanceTo(kickstance)
handle4 = row4.attachNewNode("h2")
handle4.setPos(10.33,0,0)
handle.instanceTo(handle4)

kickstance = rrow1.attachNewNode("rk1")
kickstance.setPos(23,0,0)
kicker2.instanceTo(kickstance)
handle5 = rrow1.attachNewNode("h5")
handle5.setPos(23,0,0)
handle5.setR(180)
handle.instanceTo(handle5)
block21 = rrow1.attachNewNode("b1")
block21.setPos(23,0,5.7)
blocker.instanceTo(block21)
block22 = rrow1.attachNewNode("b2")
block22.setPos(23,0,-5.7)
blocker.instanceTo(block22)


for i in range(2):
  kickstance = rrow2.attachNewNode("rk2")
  kickstance.setPos(16.33,0,i*12-6)
  kicker2.instanceTo(kickstance)
handle6 = rrow2.attachNewNode("h6")
handle6.setPos(16.33,0,0)
handle6.setR(180)
handle.instanceTo(handle6)

for i in range(5):
  kickstance = rrow3.attachNewNode("rk3")
  kickstance.setPos(4,0,i*5.5-11)
  kicker2.instanceTo(kickstance)
handle7 = rrow3.attachNewNode("h8")
handle7.setPos(4,0,0)
handle7.setR(180)
handle.instanceTo(handle7)

for i in range(3):
  kickstance = rrow4.attachNewNode("rk4")
  kickstance.setPos(-10.33,0,i*8-8)
  kicker2.instanceTo(kickstance)
handle8 = rrow3.attachNewNode("h8")
handle8.setPos(-10.33,0,0)
handle8.setR(180)
handle.instanceTo(handle8)

### Load and apply textures ############################################

texField = loader.loadTexture(DATAPATH+"textures/field2.png")
field = table.find("**/Cube")
field.setTexture(texField)

table.setTransparency(1)

texBande = loader.loadTexture(DATAPATH+"textures/bande_tex.png")
table.find("**/Cube_001").setTexture(texBande)
table.find("**/Cube_002").setTexture(texBande)
table.find("**/Cube_005").setTexture(texBande)

texKicker = loader.loadTexture(DATAPATH+"textures/kicker_tex.png")
texKicker2 = loader.loadTexture(DATAPATH+"textures/kicker2_tex.png")

if role == ROLE_SERVER:
  kicker.setTexture(texKicker)
  kicker2.setTexture(texKicker2)
else:
  kicker.setTexture(texKicker2)
  kicker2.setTexture(texKicker)
kicker.setR(180)
  
### SET UP Mouse control #############################################
base.disableMouse()

global oldx, oldy
oldx=0
oldy=0

omx =0 #opponent
omy =0
oldox=0
oldoy=0

def moveKickerTask(task):
  global oldx, oldy, omx, omy, oldox, oldoy, p1score, p2score
  if base.mouseWatcherNode.hasMouse():
    mx=base.mouseWatcherNode.getMouseX()
    my=base.mouseWatcherNode.getMouseY()  
  else:
    mx=oldx
    my=oldy
    
  if role == ROLE_CLIENT:
    sendMove(mx, my)

  if role == ROLE_SERVER:
    if task.frame==0:
      dt = task.time
    else:
      dt = task.time/task.frame * 2 # this is a global average. TODO: change to sliding window
    if dt==0: 
      dt = 0.01
  
    for i in range(STEPS):
      x = (mx * i + oldx * (STEPS-i)) / STEPS
      y = (my * i + oldy * (STEPS-i)) / STEPS
      x2 = (omx * i + oldox * (STEPS-i)) / STEPS
      y2 = (omy * i + oldoy * (STEPS-i)) / STEPS

      setKickers1(x,y)
      setKickers2(x2,y2)
    
      space.collide((world, contactgroup), near_callback)
      world.step(dt/10)
      contactgroup.empty()

  px,py,pz = ballBody.getPosition()
  rot      = ballBody.getRotation() 
  gquat    = Quat ()
  gquat.setFromMatrix (Mat3 (*rot))
  gpos     = VBase3 (px,py,pz)
  ball.setPosQuat (gpos, gquat) 
  
  oldx=mx
  oldy=my
  oldox = omx
  oldoy = omy

  ### CHECK FOR GOALS / OUTS ###############
  if (px<-28) or (px>28):
    if (px<-28):
      p2score = p2score+1
      score2.setText(P2NAME+" "+str(p2score))
    else:
      p1score = p1score+1
      score1.setText(P1NAME+" "+str(p1score))
    sendScore(p1score, p2score)
    ballBody.setPosition((0,80,0))

  if role == ROLE_SERVER:
    sendGameStatus()

  return Task.cont

def setKickers1(x,y):  #player1
  kickerZ1 = min(7.9, max(-7.9, y*10))
  kickerZ2 = min(7.9, max(-7.9, y*10))
  kickerZ3 = min(2.9, max(-2.9, y*10))
  kickerZ4 = min(5.9, max(-5.9, y*10))
  kickerR = x*250;

  row1.setZ(kickerZ1)
  row2.setZ(kickerZ2)
  row3.setZ(kickerZ3)
  row4.setZ(kickerZ4)
  kicker.setH(kickerR)
    
  kickerGeom[0].setPosition((-23, KV, kickerZ1)) 
  
  kickerGeom[1].setPosition((-16.33, KV, kickerZ2+6)) 
  kickerGeom[2].setPosition((-16.33, KV, kickerZ2-6)) 

  kickerGeom[3].setPosition((-4, KV, kickerZ3-11)) 
  kickerGeom[4].setPosition((-4, KV, kickerZ3-5.5)) 
  kickerGeom[5].setPosition((-4, KV, kickerZ3)) 
  kickerGeom[6].setPosition((-4, KV, kickerZ3+5.5))
  kickerGeom[7].setPosition((-4, KV, kickerZ3+11)) 

  kickerGeom[8].setPosition((10.33, KV, kickerZ4-8)) 
  kickerGeom[9].setPosition((10.33, KV, kickerZ4)) 
  kickerGeom[10].setPosition((10.33, KV, kickerZ4+8))

  sina = sin(kickerR * pi / 180)
  cosa = cos(kickerR * pi / 180)
  for i in range(11):
    kickerGeom[i].setRotation((cosa, -sina, 0, sina, cosa, 0, 0, 0, 1)) # yaw rotation matrix

def setKickers2(x,y):  #player2
  kicker2Z1 = min(7.9, max(-7.9, y*10))
  kicker2Z2 = min(7.9, max(-7.9, y*10))
  kicker2Z3 = min(2.9, max(-2.9, y*10))
  kicker2Z4 = min(5.9, max(-5.9, y*10))
  kicker2R = x*250;

  rrow1.setZ(kicker2Z1) #no effect currently
  rrow2.setZ(kicker2Z2)
  rrow3.setZ(kicker2Z3)
  rrow4.setZ(kicker2Z4)
  kicker2.setH(kicker2R)

  #player2
  kickerGeom2[0].setPosition((23, KV, kicker2Z1)) 

  kickerGeom2[1].setPosition((16.33, KV, kicker2Z2+6)) 
  kickerGeom2[2].setPosition((16.33, KV, kicker2Z2-6)) 

  kickerGeom2[3].setPosition((4, KV, kicker2Z3-11)) 
  kickerGeom2[4].setPosition((4, KV, kicker2Z3-5.5)) 
  kickerGeom2[5].setPosition((4, KV, kicker2Z3)) 
  kickerGeom2[6].setPosition((4, KV, kicker2Z3+5.5))
  kickerGeom2[7].setPosition((4, KV, kicker2Z3+11)) 

  kickerGeom2[8].setPosition((-10.33, KV, kicker2Z4-8)) 
  kickerGeom2[9].setPosition((-10.33, KV, kicker2Z4)) 
  kickerGeom2[10].setPosition((-10.33, KV, kicker2Z4+8))

  sina = sin(kicker2R * pi / 180)
  cosa = cos(kicker2R * pi / 180)
  for i in range(11):
    kickerGeom2[i].setRotation((cosa, -sina, 0, sina, cosa, 0, 0, 0, 1)) # yaw rotation matrix

def sendGameStatus():
  px,py,pz = ballBody.getPosition()
  prot     = ballBody.getRotation()

#  vx,vy,vz = ballBody.getLinearVel()
#  rx,ry,rz = ballBody.getAngularVel()
  
  r1,r2,r3,r4 = row1.getZ(), row2.getZ(), row3.getZ(), row4.getZ()
  o1,o2,o3,o4 = rrow1.getZ(), rrow2.getZ(), rrow3.getZ(), rrow4.getZ()
  
  rot, orot   = kicker.getH(), kicker2.getH()
  
  status = PyDatagram()
  status.addUint16(PACKET_SET)
  
  status.addFloat64(px)
  status.addFloat64(py)
  status.addFloat64(pz)
  for r in range(9): #just to be explicit
    status.addFloat64(prot[i])
#  status.addFloat64(vx)
#  status.addFloat64(vy)
#  status.addFloat64(vz)
#  status.addFloat64(rx)
#  status.addFloat64(ry)
#  status.addFloat64(rz)
  
  status.addFloat64(r1)
  status.addFloat64(r2)
  status.addFloat64(r3)
  status.addFloat64(r4)
  status.addFloat64(rot)
  
  status.addFloat64(o1)
  status.addFloat64(o2)
  status.addFloat64(o3)
  status.addFloat64(o4)
  status.addFloat64(orot)
  
  cWriter.send(status, myConnection)

def sendMove(mx, my):
  move = PyDatagram()
  move.addUint16(PACKET_MOVE)
  move.addFloat64(mx)
  move.addFloat64(my)
  cWriter.send(move, myConnection)

def sendScore(s1,s2):
  move = PyDatagram()
  move.addUint16(PACKET_SCORE)
  move.addInt16(s1)
  move.addInt16(s2)
  cWriter.send(move, myConnection)

def setGameStatus(data):
  ballBody.setPosition((-data.getFloat64(),data.getFloat64(),-data.getFloat64()))
  ballBody.setRotation((data.getFloat64(),data.getFloat64(),data.getFloat64(),data.getFloat64(),data.getFloat64(),data.getFloat64(),data.getFloat64(),data.getFloat64(),data.getFloat64())) #would we need to mirror this somehow? 
  
  px,py,pz = ballBody.getPosition() #FIXME: write this directly to ball, not ballBody. 
  rot      = ballBody.getRotation() #there's no need for physics. 
  gquat    = Quat ()
  gquat.setFromMatrix (Mat3 (*rot))
  gpos     = VBase3 (px,py,pz)
  ball.setPosQuat (gpos, gquat) 
  
  rrow1.setZ(-data.getFloat64())
  rrow2.setZ(-data.getFloat64())
  rrow3.setZ(-data.getFloat64())
  rrow4.setZ(-data.getFloat64())
  kicker2.setH(-data.getFloat64())
  
  row1.setZ(-data.getFloat64())
  row2.setZ(-data.getFloat64())
  row3.setZ(-data.getFloat64())
  row4.setZ(-data.getFloat64()) 
  kicker.setH(-data.getFloat64())
  
  
def setOpponentMove(data):
  global omx, omy
  omx = -data.getFloat64()
  omy = -data.getFloat64()
  
def setScore(data):
  global p1score, p2score
  p1score = data.getInt16()
  p2score = data.getInt16()
  score1.setText(P1NAME+" "+str(p1score))
  score2.setText(P2NAME+" "+str(p2score))
  
### RUN the game engine #########################################
run()
# this won't run the main game loop yet! (physics + mouse handling)
# this is only done when a PACKET_START is received, or the server
# is ready to start

