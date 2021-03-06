#!/usr/bin/env python

print """
  netkickern - by Thomas Hirsch 2008-2009
  This program comes with ABSOLUTELY NO WARRANTY;
  This is free software, and you are welcome to redistribute it under the
  conditions of the GNU General Public Licence version 3 (GPLv3)
  see: http://www.gnu.org/licenses/gpl-3.0.html
"""

import os

SEPARATOR = os.path.normpath('/');              # find out what a SEPARATOR looks like on this os
DATAPATH = "." + SEPARATOR + "data" + SEPARATOR # where to find data files (.x models)

PORT=5036          # default port to use for connections

STEPS = 15         # each mouse movement is divided into STEPS steps, to keep physics changes smooth. 10 feels good
                   # lower this for slower computers - however, fast mouse movements may not be correctly recognized

MOUSEX_SPEED = 250 # increase this to make horizontal movements faster
MOUSEY_SPEED = 10  # increase this to make vertical movements faster

Y_STICKINESS = 100 # how much the ball assumes vertical movements of the kicker upon contact

TEAMNAME = None    # To be set according to role or config file - not actually a const. 
P1NAME = "NONAMES" # default team name for the server.
P2NAME = "DUMMIES" # default team name for the client.

### list of used packet types #######################################
PACKET_HELLO = 0   # identification using magic word
PACKET_SCORE = 1   # send a score update to client
PACKET_PING  = 2   # measure round trip time
PACKET_PONG  = 3   # measure round trip time
PACKET_START = 4   # start game notification
PACKET_MOVE  = 5   # movement update client -> server
PACKET_SET   = 6   # physics & movement update, server -> client

PACKET_QPREF = 10  # query for client preferences
PACKET_PREF  = 11  # reply with client preferences
PACKET_ROLE  = 12  # assign a client role
PACKET_NAME  = 13  # name a team
PACKET_PLACE = 14  # place a player at another position on the table (0-3)

PACKET_RESET = 20  # suggest to reset ball position
PACKET_MSG   = 21  # send a custom message to another player
#####################################################################

MAGIC_WORD   = "kickern?"
PROTOCOL_VERSION = 9                              # to be increased with each protocol change
SOFTWARE_VERSION = "svn"+'$Revision$'[11:-2] # automatically set by subversion on checkout

ROLE_SERVER  = 1
ROLE_CLIENT  = 2

STATUS_CONF  = 0   #TODO: use this to implement proper protocol states
STATUS_INIT  = 1
STATUS_LIVE  = 2 

COLCAT_BALL   = 1  # arbitrary category bit. used to determine who can collide with whom. This is the ball - default category
COLCAT_WALL   = 2  # arbitrary category bit. used to determine who can collide with whom. 
COLCAT_KICKER = 4  # arbitrary category bit. used to determine who can collide with whom. 
COLCAT_FIELD  = 8  # arbitrary category bit. used to determine who can collide with whom. 

MODE_TRAINING = 1  # Training mode. No network communication, player controls all handles 
MODE_2P       = 2  # 2P network mode. Each player controls four handles.
MODE_4P       = 4  # 4P network mode. Each player controls two handles.

mode = MODE_2P

lastResetRequest = 0 # timestamp: partner requested reset via UDP
lastResetPress   = 0 # timestamp: player requested reset via key press

playerPrefs = {}
# shall contain per player preferences. currently:
# team      - team name
# pos       - position on the table
# lastReset - last reset request
####
POSITION = [0]+[None]*3
# Players on this position in 4P mode, 0 = server, 1-3 = clients according to connection order on server side
# TEAM 2: 3   2  (index 0, 2 is defense)
#         TABLE  (index 1, 3 is offense)
# TEAM 1: 0   1 
MY_POSITION = 0

print "Debug information:"
print "  You are using software revision "+SOFTWARE_VERSION
print "  This software uses network protocol version "+str(PROTOCOL_VERSION)
print ""

### IMPORTS ###########################################################

import ode
import sys
import time

from random import random
from math import sin, cos, pi, atan2, sqrt

def sgn(x):
  if x==0:
    return 0
  else:
    return x/abs(x)

from pandac.PandaModules import *
from direct.distributed.PyDatagram import PyDatagram 
from direct.distributed.PyDatagramIterator import PyDatagramIterator 

from ConfigParser import ConfigParser
#more imports after network setup!

### Read configuration parameters #####################################

status = STATUS_CONF

try:
  config = ConfigParser()
  config.read(['kickern.conf', 'kickern.ini'])
  TEAMNAME = config.get('team','name')
  messages=[]
  messages.append(config.get('messages','f1'))
  messages.append(config.get('messages','f2'))
  messages.append(config.get('messages','f3'))
  messages.append(config.get('messages','f4'))
  messages.append(config.get('messages','f5'))
  messages.append(config.get('messages','f6'))
  messages.append(config.get('messages','f7'))
  messages.append(config.get('messages','f8'))
  messages.append(config.get('messages','f9'))
  messages.append(config.get('messages','f10'))
  messages.append(config.get('messages','f11'))
  messages.append(config.get('messages','f12'))
except:
  pass

### Network handling functions#########################################
def startGame():
  taskMgr.add(moveKickerTask, "gameTask");
  if role==ROLE_SERVER and not (mode==MODE_TRAINING):
    taskMgr.add(pingTask, "pingTask"); # not needed, currently. enable to determine rtt (deltatime)
   
def tskReaderPolling(taskdata):
  while cReader.dataAvailable():
    datagram=NetDatagram()  # catch the incoming data in this instance
    # Check the return value; if we were threaded, someone else could have
    # snagged this data before we did
    if cReader.getData(datagram):
      myProcessDataFunction(datagram) 
  return Task.cont

def toAll(packet, connections):
  for con in connections:
    cWriter.send(packet, con)

def pingTask(task):
  if (task.frame % 1000) > 0: #determine network delay every now and then (every 1000 frames)
    return Task.cont
  ping = PyDatagram()
  ping.addUint16(PACKET_PING)
  ping.addFloat64(time.time())
  toAll(ping, activeConnections)
  return Task.cont

def myProcessDataFunction(datagram):
  global status, P1NAME, P2NAME, lastResetRequest
  global MY_POSITION, kicker, texKicker, texKicker2, mode

  if (role==ROLE_SERVER):
    sender = activeConnections.index(datagram.getConnection()) 
  data = PyDatagramIterator(datagram)
  #try:
  if True: #just to keep the indent, in case we need "try" again. 
    pktType = data.getUint16()
    if role==ROLE_SERVER: # packets received only by server
      if pktType==PACKET_MOVE:
        setOpponentMove(data, sender+1)
      elif pktType==PACKET_MSG:
        timer = data.getUint16()
        msg   = data.getString()
        sendMessage(msg, timer) #broadcast to all
      elif pktType==PACKET_HELLO:
        magic = data.getString()
        proto = data.getUint16()
        soft  = data.getString()
        if magic != MAGIC_WORD:
          print "Connecting party did not identify as netkickern client."
          sys.exit(1)
        if proto != PROTOCOL_VERSION:
          print "Connecting party used incompatible protocol version "+str(proto)+"."
          print "We are using "+str(PROTOCOL_VERSION)+"."
          sys.exit(1)
        if soft != SOFTWARE_VERSION:
          print "WARNING: Client is using software "+soft+"."
        print "Ok, client "+str(sender+1)+" connected."
        status = STATUS_INIT
        qpref = PyDatagram() #query for client preferences
        qpref.addUint16(PACKET_QPREF)
        qpref.addString(SOFTWARE_VERSION)
        cWriter.send(qpref, activeConnections[sender])
      elif pktType==PACKET_PREF:
        if status != STATUS_INIT:
          return
        prefs = {}
        teamname = data.getString()
        prefs['team']=teamname
        place = -1
        if (mode == MODE_4P):
          #assign the last free position, and P1 only if the teamname matches or everything else is given away
          if not POSITION[3]:
            place = 3
          if not POSITION[2]:
            place = 2
          if (teamname == TEAMNAME) or (place==-1):
            if not POSITION[1]:
              place = 1
          print "placed player ", sender+1, " at position ", place
          POSITION[place]=sender+1
          prefs['pos'] = place
        playerPrefs[sender]=prefs
        if (mode == MODE_2P) or (0 in playerPrefs and 1 in playerPrefs and 2 in playerPrefs):
          P1NAME = TEAMNAME
          P2NAME = playerPrefs[0]['team']
          rename = PyDatagram() 
          rename.addUint16(PACKET_NAME)
          rename.addString(P1NAME) 
          rename.addString(P2NAME) 
          toAll(rename, activeConnections)
          if (mode == MODE_4P): #inform players of the position they play in
            for i in range(0,3):
              placing = PyDatagram()
              placing.addUint16(PACKET_PLACE)
              placing.addUint16(playerPrefs[i]['pos'])
              cWriter.send(placing, activeConnections[i])
          resetNames()
          welcome = PyDatagram()
          welcome.addUint16(PACKET_START)
          toAll(welcome, activeConnections)
          startGame()
      elif pktType==PACKET_PONG:
        stime = data.getFloat64()
        now = time.time()
        deltatime = now-stime   # TODO: use this to delay mouse movements by avg(deltatime)/2
        print "player "+str(sender)+" network delay: "+str(deltatime*500)+"ms " #rtt/2
      elif pktType==PACKET_RESET:
        lastResetRequest = time.time()
        playerPrefs[sender]['lastReset']=lastResetRequest
        if not isResetConfirmed():
          resetRequest=PyDatagram() #forward to all clients 
          resetRequest.addUint16(PACKET_RESET)
          #resetRequest.addUint16(sender) # TODO: tell everyone which player sent the request
          toAll(resetRequest, activeConnections) 
          setMessage("Player "+str(sender+1)+" wishes to reset the ball.\nPress Space to confirm.", 3)
    else: # packets received only by clients
      if pktType==PACKET_SET:
        setGameStatus(data)
      elif pktType==PACKET_SCORE:
        setScore(data)
      elif pktType==PACKET_QPREF:
        soft = data.getString()
        if soft != SOFTWARE_VERSION:
          print "WARNING: Server is using software "+soft+"."
        status = STATUS_INIT
        pref = PyDatagram()
        pref.addUint16(PACKET_PREF)
        pref.addString(TEAMNAME)
        cWriter.send(pref, serverConnection)     
      elif pktType==PACKET_START:
        print "connection to game host confirmed."
        startGame()
      elif pktType==PACKET_MSG:
        timer = data.getUint16()
        msg   = data.getString()
        setMessage(msg, timer)
      elif pktType==PACKET_NAME:
        P1NAME = data.getString()
        P2NAME = data.getString()
        resetNames()
      elif pktType==PACKET_PLACE: #4P only
        MY_POSITION = data.getUint16()
        mode = MODE_4P
        resetGameColours(kicker, texKicker, texKicker2)  
      elif pktType==PACKET_PING:
        stime = data.getFloat64()
        pong = PyDatagram()
        pong.addUint16(PACKET_PONG)
        pong.addFloat64(stime)
        cWriter.send(pong, serverConnection)
      elif pktType==PACKET_RESET:
        setMessage("Another wishes to reset the ball.\nPress Space to confirm.", 3)
  #except Exception, e:
  #  print e 
  #  sys.exit(1) #wow, this is what I call exception handling.. 
  return

### Define network role ###############################################
role = ROLE_SERVER 
if len(sys.argv)>1:
  if sys.argv[1]=='-4':
    mode = MODE_4P
    print "Server mode. 4 player mode." 
  else:
    role   = ROLE_CLIENT
    server = sys.argv[1]
    print "Client mode." 

cManager = QueuedConnectionManager()
cReader  = QueuedConnectionReader(cManager, 0)
cWriter  = ConnectionWriter(cManager,0)

activeConnections = False # all connections to clients
serverConnection  = False # connection to a server only

if role == ROLE_SERVER:
  if TEAMNAME is None:
    TEAMNAME=P1NAME
  else:
    P1NAME=TEAMNAME
  cListener = QueuedConnectionListener(cManager, 0)
  activeConnections=[] # We'll want to keep track of these later
  tcpSocket = cManager.openTCPServerRendezvous(PORT,1000)
  cListener.addConnection(tcpSocket)

  print "====================================="
  if mode == MODE_4P:
    print "waiting for opponents to connect.  "
  else:
    print "waiting for opponent to connect.  "
    print "or press Ctrl+C to enter training.   "
  print "====================================="
  try:
    waitfor = (mode == MODE_2P) and 1 or 3
    while len(activeConnections) < waitfor:
      while not cListener.newConnectionAvailable():
        time.sleep(0.1)
      rendezvous = PointerToConnection()
      netAddress = NetAddress()
      myConnection = PointerToConnection()

      if cListener.getNewConnection(rendezvous,netAddress,myConnection):
        myConnection = myConnection.p()
        activeConnections.append(myConnection) # Remember connection
        cReader.addConnection(myConnection)    # Begin reading connection
        print "Players connected :"+str(len(activeConnections))

  except KeyboardInterrupt:
    print "aborted."
    if mode==MODE_2P:
      print "Switching to single player (training) mode."
      mode = MODE_TRAINING
    else:
      #FIXME: close open connections, maybe notify clients
      sys.exit(1)

else: 
  if not TEAMNAME:
    TEAMNAME=P2NAME
  serverConnection=cManager.openTCPClientConnection(server,PORT,3000)
  if serverConnection:
    cReader.addConnection(serverConnection)    # receive messages from server
    welcome = PyDatagram()
    welcome.addUint16(PACKET_HELLO)
    welcome.addString(MAGIC_WORD)          # the magic word to initiate a game.
    welcome.addUint16(PROTOCOL_VERSION) 
    welcome.addString(SOFTWARE_VERSION) 
    cWriter.send(welcome, serverConnection)

  if not serverConnection:
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
textFormat(score1)
textNodePath1 = aspect2d.attachNewNode(score1)
textNodePath1.setScale(0.10)

p2score = 0
score2 = TextNode('t2score')
textFormat(score2)
textNodePath2 = aspect2d.attachNewNode(score2)
textNodePath2.setScale(0.10)

message = TextNode('message')
message.setText("")
message.setAlign(TextNode.ACenter)
textFormat(message)
textNodePath3 = aspect2d.attachNewNode(message)
textNodePath3.setScale(0.10)
textNodePath3.setPos(VBase3(0,0,-.85))

def resetNames():
  score1.setText(P1NAME+"  "+str(p1score))
  score2.setText(P2NAME+"  "+str(p2score))
resetNames()

def setMessage(text, timer):
  message.setText(text)
  if timer>0:
    taskMgr.doMethodLater(timer, setMessage, 'resetMessage', extraArgs=["",0])

def sendMessage(text, timer):
  if not mode==MODE_TRAINING:
    msg = PyDatagram() #send message packet
    msg.addUint16(PACKET_MSG)
    msg.addUint16(timer)
    msg.addString(text)
    if role==ROLE_SERVER:
      toAll(msg, activeConnections)
      setMessage(text, timer)
    else:
      cWriter.send(msg, serverConnection)     
  
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
if not mode==MODE_TRAINING:
  taskMgr.add(tskReaderPolling,"Poll the connection reader",-40)

### Setup pyODE ########################################################
world = ode.World()
space = ode.Space()
contactgroup = ode.JointGroup()

world.setGravity((0,9.81,0))
world.setContactSurfaceLayer(0.01)

## define ball
ballBody = ode.Body(world)
ballMass = ode.Mass()
ballMass.setSphere(250,0.8)
ballBody.setMass(ballMass)
ballGeom = ode.GeomSphere(space, radius=0.8)
ballGeom.setBody(ballBody)
# place ball
ballBody.setPosition((-3,75,0))

ballGeom.setCategoryBits(COLCAT_BALL)
ballGeom.setCollideBits (COLCAT_WALL + COLCAT_KICKER + COLCAT_FIELD)

## define table
#tableGeom = ode.GeomBox(space, (28,8,8)) #theoretical extents
tableGeom = ode.GeomBox(space, (56,1,32)) #trial and error

tableGeom.setCategoryBits(COLCAT_FIELD)
tableGeom.setCollideBits (0) #one way suffices

baseheight = 82.4   #trial and error
# baseheight = 85.7 #theory
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

for geom in wallGeom:
  geom.setCategoryBits(COLCAT_WALL)
  geom.setCollideBits (0) #one way suffices

## define kickers
kickerGeom = []
KV = 79 #"const" vertical height of kickers
for i in range(11):
  kickerGeom.append(ode.GeomBox(space,(2*0.65, 6.36*0.65, 1.5*0.65))) # exxagerated y height to [-3,18,3,18], actually should be [1.14, -3.18]
                                                                    # y position still has to be off-centered
  kickerGeom[i].setPosition((10,KV,10)) #just some random position. should be reassigned by mouse movement asap.

kickerGeom2 = []
for i in range(11):
  kickerGeom2.append(ode.GeomBox(space,(2*0.65, 6.36*0.65, 1.5*0.65))) #exxagerated y height to [-3,18,3,18], actually should be [1.14, -3.18]
                                                                     # y position still has to be off-centered
  kickerGeom2[i].setPosition((10,KV,10)) #just some random position. should be reassigned by mouse movement asap.

for geom in kickerGeom+kickerGeom2:
  geom.setCategoryBits(COLCAT_KICKER)
  geom.setCollideBits (0) #one way suffices

BLOCK = [False]*4
mouseAy = [0]*4

def near_callback(args, geom1, geom2):
  ##TODO: 4P generalization
  global BLOCK, kicker, mouseAy
  #global called
  
  #called = called + 1
  
  contacts=ode.collide(geom1, geom2)
  world, contactgroup = args
  for c in contacts:
    
    #if not ((geom1 == ballGeom) or (geom2 == ballGeom)):
    #  print "rong collision!"
    
    if (geom1 in kickerGeom) or (geom2 in kickerGeom) or (geom1 in kickerGeom2) or (geom2 in kickerGeom2):
      c.setMu(1E5)     #kickers have high friction, minimal bounce - FIXME: does not work. you still can't stop balls
      c.setBounce(1) 
      #===================================================================================================================#
      #replace the following line with "if True:" to skip fake ball handling
      if (geom1 in kickerGeom and geom2 in kickerGeom2) or (geom1 in kickerGeom2 and geom2 in kickerGeom2):
        pass
      else:
        bx, by, bz = ballBody.getPosition()
        ax, ay, az = ballBody.getLinearVel()
        px, py, pz = c.getContactGeomParams()[0]
        angle = 0
        if geom1 in kickerGeom or geom2 in kickerGeom:
          if abs(pz-bz)<0.1: #if the ball touches the kicker on its left or right
            if (bx<-10):
              ballBody.setLinearVel((ax,ay,(az+mouseAy[0])/2)) #causes some stickiness in the vertical axis
              angle = kicker[0].getH()
              if (by>py) and (((angle < -45) and (angle>-90)) or ((angle > 45) and (angle<90))):
                BLOCK[0] = True
                ballBody.setLinearVel((ax/3, ay, (az+mouseAy[0])/2))
            else:
              ballBody.setLinearVel((ax,ay, (az+mouseAy[1])/2)) #causes some stickiness in the vertical axis
              angle = kicker[1].getH()
              if (by>py) and (((angle < -45) and (angle>-90)) or ((angle > 45) and (angle<90))):
                BLOCK[1] = True
                ballBody.setLinearVel((ax/3, ay, (az+mouseAy[1])/2))
        else:
          if abs(pz-bz)<0.1: #if the ball touches the kicker on its left or right
            if (bx>10):
              ballBody.setLinearVel((ax, ay, (az+mouseAy[2])/2)) #causes some stickiness in the vertical axis
              angle = kicker[2].getH()
              if (by>py) and (((angle < -45) and (angle>-90)) or ((angle > 45) and (angle<90))):
                BLOCK[2] = True
                ballBody.setLinearVel((ax/3, ay, (az+mouseAy[2])/2))
            else:
              ballBody.setLinearVel((ax, ay, (az+mouseAy[3])/2)) #causes some stickiness in the vertical axis
              angle = kicker[3].getH()
              if (by>py) and (((angle < -45) and (angle>-90)) or ((angle > 45) and (angle<90))):
                BLOCK[3] = True
                ballBody.setLinearVel((ax/3, ay, (az+mouseAy[3])/2))
      #===================================================================================================================#
    elif (geom1 == tableGeom) or (geom2 == tableGeom): 
      c.setMu(4)    #table has little bounce, noticeable friction
      c.setBounce(1.5) 
    elif (geom1 in wallGeom) or (geom2 in wallGeom):
      c.setMu(1)      #walls have ok bounce, noticeable friction
      c.setBounce(2)
    else:             #ignore anything else. I have no idea what that could be
      print "something unidentified collided with my balls. ouch."
      continue 
    j=ode.ContactJoint(world, contactgroup, c)
    j.attach(geom1.getBody(), geom2.getBody())

### place CAMERA ######################################################
#default camera
cameraAngle = 45

def setCamera(diff = 0):
  global cameraAngle
  cameraAngle = cameraAngle + diff
  base.camera.setHpr(0,cameraAngle,0) #45deg angle sideways
  base.camera.setPos(0,80-80*cos(cameraAngle*pi/180),0-80*sin(cameraAngle*pi/180))

setCamera()

#base.camera.setHpr(0,25,0) #25deg angle sideways
#base.camera.setPos(0,0,-35)

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

kicker=[None]*4
for i in range(0,4):
  kicker[i] = loader.loadModel(DATAPATH+"models/kicker.x") #FIXME: this could just as well be a single instance
  kicker[i].setScale(.65,.65,.65)
  kicker[i].setPos(0,79.5,0)

handle  = loader.loadModel(DATAPATH+"models/handle.x")
blocker = loader.loadModel(DATAPATH+"models/blocker.x")
handle.setPos(0,80,0)
handle.setScale(1,1,.7)
blocker.setPos(0,80,0)
blocker.setScale(.8,.8,1)

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
kicker[0].instanceTo(kickstance)
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
  kicker[0].instanceTo(kickstance)
handle2 = row2.attachNewNode("h2")
handle2.setPos(-16.33,0,0)
handle.instanceTo(handle2)

for i in range(5):
  kickstance = row3.attachNewNode("k3")
  kickstance.setPos(-4,0,i*5.5-11)
  kicker[1].instanceTo(kickstance)
handle3 = row3.attachNewNode("h2")
handle3.setPos(-4,0,0)
handle.instanceTo(handle3)

for i in range(3):
  kickstance = row4.attachNewNode("k4")
  kickstance.setPos(10.33,0,i*8-8)
  kicker[1].instanceTo(kickstance)
handle4 = row4.attachNewNode("h2")
handle4.setPos(10.33,0,0)
handle.instanceTo(handle4)

kickstance = rrow1.attachNewNode("rk1")
kickstance.setPos(23,0,0)
kicker[2].instanceTo(kickstance)
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
  kicker[2].instanceTo(kickstance)
handle6 = rrow2.attachNewNode("h6")
handle6.setPos(16.33,0,0)
handle6.setR(180)
handle.instanceTo(handle6)

for i in range(5):
  kickstance = rrow3.attachNewNode("rk3")
  kickstance.setPos(4,0,i*5.5-11)
  kicker[3].instanceTo(kickstance)
handle7 = rrow3.attachNewNode("h8")
handle7.setPos(4,0,0)
handle7.setR(180)
handle.instanceTo(handle7)

for i in range(3):
  kickstance = rrow4.attachNewNode("rk4")
  kickstance.setPos(-10.33,0,i*8-8)
  kicker[3].instanceTo(kickstance)
handle8 = rrow3.attachNewNode("h8")
handle8.setPos(-10.33,0,0)
handle8.setR(180)
handle.instanceTo(handle8)

render.setAntialias(AntialiasAttrib.MMultisample) # enable antialiasing for all objects

### Load and apply textures ############################################

def resetGameColours(kickers, texture1, texture2):
  if role == ROLE_SERVER or MY_POSITION == 1:
    kickers[0].setTexture(texture1)
    kickers[1].setTexture(texture1)
    kickers[2].setTexture(texture2)
    kickers[3].setTexture(texture2)
  else:
    kickers[0].setTexture(texture2)
    kickers[1].setTexture(texture2)
    kickers[2].setTexture(texture1)
    kickers[3].setTexture(texture1)

texField = loader.loadTexture(DATAPATH+"textures/field2.png")
texBande = loader.loadTexture(DATAPATH+"textures/bande_tex.png")
texKicker = loader.loadTexture(DATAPATH+"textures/kicker_tex.png")
texKicker2 = loader.loadTexture(DATAPATH+"textures/kicker2_tex.png")

table.setTransparency(1)
try: 
  field = table.find("**/Cube")
  field.setTexture(texField)

  table.find("**/Cube_001").setTexture(texBande)
  table.find("**/Cube_002").setTexture(texBande)
  table.find("**/Cube_005").setTexture(texBande)

  resetGameColours(kicker, texKicker, texKicker2)  
  kicker[0].setR(180)
  kicker[1].setR(180)
except Exception, e:
  print texBande #good for some DEBUG output
  print e
  #no textures then it shall be.
  pass

### SET UP Keyboard control ##########################################

def doReset():
  global lastResetPress, lastResetRequest
  
  px = ballBody.getPosition()[0]
  ballBody.setPosition((sgn(px)*3,75,0)) #on the side the ball is 
  ballBody.setLinearVel((0,0,0))
  #FIXME: implement correct reset rules
  
  setMessage("", 3) #remove any existing messages
  lastResetPress, lastResetRequest = 0, 0
  
  
def isResetConfirmed():
  global lastResetPress, lastResetRequest
  if mode==MODE_TRAINING:
    doReset()
    return True
  now = time.time()
  if lastResetPress > now - 3.0 and lastResetRequest > now - 3.0:
    doReset()
    return True
  else:
    return False

def checkReset():
  global lastResetPress
  lastResetPress = time.time()
  reset = PyDatagram() #send a reset request to partner
  reset.addUint16(PACKET_RESET)
  if role==ROLE_CLIENT: 
    cWriter.send(reset, serverConnection)
  elif role == ROLE_SERVER and not isResetConfirmed():
    toAll(reset, activeConnections)

base.accept('escape', sys.exit )             #exit on esc
base.accept('arrow_up', setCamera, [-5])
base.accept('arrow_down', setCamera, [5])
base.accept('arrow_up-repeat', setCamera, [-5])
base.accept('arrow_down-repeat', setCamera, [5])
base.accept('space', checkReset ) 
base.accept('r',     checkReset ) 
try:
  base.accept('f1', sendMessage, [messages[0],3])
  base.accept('f2', sendMessage, [messages[1],3])
  base.accept('f3', sendMessage, [messages[2],3])
  base.accept('f4', sendMessage, [messages[3],3])
  base.accept('f5', sendMessage, [messages[4],3])
  base.accept('f6', sendMessage, [messages[5],3])
  base.accept('f7', sendMessage, [messages[6],3])
  base.accept('f8', sendMessage, [messages[7],3])
  base.accept('f9', sendMessage, [messages[8],3])
  base.accept('f10', sendMessage, [messages[9],3])
  base.accept('f11', sendMessage, [messages[10],3])
  base.accept('f12', sendMessage, [messages[11],3])
except:
  pass
  
### SET UP Mouse control #############################################
base.disableMouse()

#global oldx, oldy
mx =[0]*4  #mouse positions
my =[0]*4
oldx=[0]*4 #previous positions
oldy=[0]*4

def setKickers(pos,x,y):  #TODO: clean up code when this is tested
  if pos==0:
    setKickers0(x,y)
  elif pos==1:
    setKickers1(x,y)
  elif pos==2:
    setKickers2(x,y)
  elif pos==3:
    setKickers3(x,y)
  #ouch!

def setKickers0(x,y):  #position 0 
  kickerZ1 = min(7.9, max(-7.9, y))
  kickerZ2 = min(7.9, max(-7.9, y))
  row1.setZ(kickerZ1)
  row2.setZ(kickerZ2)
  
  kickerR = x;
  kicker[0].setH(kickerR)  

  kickerGeom[0].setPosition((-23, KV, kickerZ1)) 
  
  kickerGeom[1].setPosition((-16.33, KV, kickerZ2+6)) 
  kickerGeom[2].setPosition((-16.33, KV, kickerZ2-6)) 

  sina = sin(kickerR * pi / 180)
  cosa = cos(kickerR * pi / 180)
  for i in range(0,3):
    kickerGeom[i].setRotation((cosa, -sina, 0, sina, cosa, 0, 0, 0, 1)) # yaw rotation matrix

def setKickers1(x,y):  #position 1
  kickerZ3 = min(2.9, max(-2.9, y))
  kickerZ4 = min(5.9, max(-5.9, y))
  row3.setZ(kickerZ3)
  row4.setZ(kickerZ4)
  
  kickerR = x;
  kicker[1].setH(kickerR) 

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
  for i in range(3,11):
    kickerGeom[i].setRotation((cosa, -sina, 0, sina, cosa, 0, 0, 0, 1)) # yaw rotation matrix

def setKickers2(x,y):  #position 2
  kicker2Z1 = min(7.9, max(-7.9, y))
  kicker2Z2 = min(7.9, max(-7.9, y))
  rrow1.setZ(kicker2Z1) 
  rrow2.setZ(kicker2Z2)
  
  kicker2R = x;
  kicker[2].setH(kicker2R)
  
  kickerGeom2[0].setPosition((23, KV, kicker2Z1)) 

  kickerGeom2[1].setPosition((16.33, KV, kicker2Z2+6)) 
  kickerGeom2[2].setPosition((16.33, KV, kicker2Z2-6)) 
  
  sina = sin(kicker2R * pi / 180)
  cosa = cos(kicker2R * pi / 180)
  for i in range(0,3):
    kickerGeom2[i].setRotation((cosa, -sina, 0, sina, cosa, 0, 0, 0, 1)) # yaw rotation matrix

def setKickers3(x,y):  #position 3
  kicker2Z3 = min(2.9, max(-2.9, y))
  kicker2Z4 = min(5.9, max(-5.9, y))
  rrow3.setZ(kicker2Z3)
  rrow4.setZ(kicker2Z4)
  
  kicker2R = x;
  kicker[3].setH(kicker2R) 

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
  for i in range(3,11):
    kickerGeom2[i].setRotation((cosa, -sina, 0, sina, cosa, 0, 0, 0, 1)) # yaw rotation matrix

setKickers0(0,0)
setKickers1(0,0)
setKickers2(0,0)
setKickers3(0,0)

blockx=[0]*4

def moveKickerTask(task):
  global oldx, oldy, mx, my, p1score, p2score
  global BLOCK, blockx
  global mouseAy
  #global called
  
  if base.mouseWatcherNode.hasMouse():
    mx[MY_POSITION]=base.mouseWatcherNode.getMouseX() * MOUSEX_SPEED
    my[MY_POSITION]=base.mouseWatcherNode.getMouseY() * MOUSEY_SPEED
  else:
    mx[MY_POSITION]=oldx[MY_POSITION]
    my[MY_POSITION]=oldy[MY_POSITION]
    
  if mode==MODE_TRAINING:
    for i in range(1,4):
      mx[i], my[i] = mx[0], my[0]
    
  if role == ROLE_CLIENT:
    sendMove(mx[MY_POSITION], my[MY_POSITION])

  if role == ROLE_SERVER:
    if mode==MODE_2P:
      mx[1], my[1] = mx[0], my[0]
      
    if task.frame==0:
      dt = task.time
    else:
      dt = task.time/task.frame * 2 # this is a global average. TODO: change to sliding window
    if dt==0: 
      dt = 0.01
  
    step = STEPS * Y_STICKINESS
    x=[0]*4
    y=[0]*4
    for i in range(0,4):
      mouseAy[i]=(my[i]-oldy[i]) / step
    for j in range(STEPS):
      BLOCK = [False]*4
      x = [0]*4
      y = [0]*4
      for i in range(0,4):
        x[i] = (mx[i] * j + oldx[i] * (STEPS-j)) / STEPS
        y[i] = (my[i] * j + oldy[i] * (STEPS-j)) / STEPS

        setKickers(i,x[i],y[i])

      space.collide((world, contactgroup), near_callback)
      world.step(dt/10)
      contactgroup.empty()

      for i in range(0,4):
        if BLOCK[i]:
          setKickers(i,blockx[i],y[i])
        else:
          blockx[i] = x[i]
    
  px,py,pz = ballBody.getPosition()
  rot      = ballBody.getRotation() 
  gquat    = Quat ()
  gquat.setFromMatrix (Mat3 (*rot))
  gpos     = VBase3 (px,py,pz)
  ball.setPosQuat (gpos, gquat)
  
  oldx=mx[:]
  oldy=my[:]

  ### CHECK FOR GOALS / OUTS ###############
  if (px<-28) or (px>28):
    if (py>75): #under the bar
      if (px<-28):
        p2score = p2score+1
        score2.setText(P2NAME+" "+str(p2score))
      else:
        p1score = p1score+1
        score1.setText(P1NAME+" "+str(p1score))
      if not mode==MODE_TRAINING:
        sendScore(p1score, p2score)
    ballBody.setPosition((sgn(px)*3,75,0)) #on the side the ball went out
    ballBody.setLinearVel((0,0,0))

  if role == ROLE_SERVER and not mode==MODE_TRAINING:
    sendGameStatus()

  return Task.cont


def sendGameStatus():
  px,py,pz = ballBody.getPosition()
  prot     = ballBody.getRotation()

  r1,r2,r3,r4 = row1.getZ(), row2.getZ(), row3.getZ(), row4.getZ()
  o1,o2,o3,o4 = rrow1.getZ(), rrow2.getZ(), rrow3.getZ(), rrow4.getZ()
  
  rot = [None]*4
  for i in range(0,4):
    rot[i] = kicker[i].getH()
  
  status = PyDatagram()
  status.addUint16(PACKET_SET)
  
  status.addFloat64(px)
  status.addFloat64(py)
  status.addFloat64(pz)
  for r in range(9): #just to be explicit
    status.addFloat64(prot[i])
  
  status.addFloat64(r1)
  status.addFloat64(r2)
  status.addFloat64(r3)
  status.addFloat64(r4)
  
  status.addFloat64(o1)
  status.addFloat64(o2)
  status.addFloat64(o3)
  status.addFloat64(o4)

  for i in range(0,4):
    status.addFloat64(rot[i])
  
  toAll(status, activeConnections)

def sendMove(mx, my):
  move = PyDatagram()
  move.addUint16(PACKET_MOVE)
  sgn = (mode == MODE_2P or MY_POSITION>1) and -1 or 1
  move.addFloat64(sgn*mx)
  move.addFloat64(sgn*my)
  cWriter.send(move, serverConnection)

def sendScore(s1,s2):
  move = PyDatagram()
  move.addUint16(PACKET_SCORE)
  move.addInt16(s1)
  move.addInt16(s2)
  toAll(move, activeConnections)

def setGameStatus(data):
  sgn = (mode == MODE_2P or MY_POSITION>1) and -1 or 1
  #print "sgn",sgn,MY_POSITION,mode
  ballBody.setPosition((sgn*data.getFloat64(),data.getFloat64(),sgn*data.getFloat64()))
  ballBody.setRotation((data.getFloat64(),data.getFloat64(),data.getFloat64(),data.getFloat64(),data.getFloat64(),data.getFloat64(),data.getFloat64(),data.getFloat64(),data.getFloat64())) #would we need to mirror this somehow? 
  
  px,py,pz = ballBody.getPosition() #FIXME: write this directly to ball, not ballBody. 
  rot      = ballBody.getRotation() #there's no need for physics. 
  gquat    = Quat ()
  gquat.setFromMatrix (Mat3 (*rot))
  gpos     = VBase3 (px,py,pz)
  ball.setPosQuat (gpos, gquat) 
  
  if (sgn==-1): #TODO: Clean up this if-block
    rrow1.setZ(-data.getFloat64())
    rrow2.setZ(-data.getFloat64())
    rrow3.setZ(-data.getFloat64())
    rrow4.setZ(-data.getFloat64())
  
    row1.setZ(-data.getFloat64())
    row2.setZ(-data.getFloat64())
    row3.setZ(-data.getFloat64())
    row4.setZ(-data.getFloat64()) 
    
    for i in range(0,4):
      angle = -data.getFloat64()
      kicker[(2+i)%4].setH(angle)
  else:
    row1.setZ(data.getFloat64())
    row2.setZ(data.getFloat64())
    row3.setZ(data.getFloat64())
    row4.setZ(data.getFloat64())
  
    rrow1.setZ(data.getFloat64())
    rrow2.setZ(data.getFloat64())
    rrow3.setZ(data.getFloat64())
    rrow4.setZ(data.getFloat64()) 

    for i in range(0,4):
      angle = data.getFloat64()
      kicker[i].setH(angle)
  
def setOpponentMove(data, sender):
  global mx, my
  if (mode == MODE_4P):
    mx[sender] = data.getFloat64()
    my[sender] = data.getFloat64()
  elif (mode==MODE_2P):
    mx[3] = mx[2] = data.getFloat64()
    my[3] = my[2] = data.getFloat64()
  
def setScore(data):
  global p1score, p2score
  p1score = data.getInt16()
  p2score = data.getInt16()
  score1.setText(P1NAME+" "+str(p1score))
  score2.setText(P2NAME+" "+str(p2score))
  
### RUN the game engine #########################################
# unless in training mode, this won't run the main game loop yet! (physics + mouse handling)
# this is only done when a PACKET_START is received, or the server is ready to start
if mode==MODE_TRAINING: 
  startGame()
run()


