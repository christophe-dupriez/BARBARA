import time
import datetime
import subprocess
import select
import re
import traceback
import threading
from Queue import Queue,Empty,Full
from Configuration import AllScanners, Scanner

SCAN_SECONDS = 60

class bluetoothScanner():

    handle = None
    startScan = None
    pairing = False
    toBePaired = None
    config = None
    screen = None
    alive = True
    ready = False
    commandFIFO = []
    aQueue = None
    todo = {}
    currTodo = None
    currInfo = None

    def rePairingDevice(self):
        if self.pairing:
            print("Already pairing...")
            return
        if self.handle:
            for aScanner in self.config.AllScanners.elements:
                currScanner = self.config.AllScanners.elements[aScanner]
                if currScanner.paired and currScanner.isActive():
                    currScanner.paired = False
                    self.pushCommand("disconnect "+aScanner.id+"\n")
                currScanner.paired = False
            self.pushCommand("paired-devices\n")
            self.pairingDevice()

    def pairingDevice(self):
        if self.pairing:
            print("Already pairing...")
            return
        if self.handle:
            if not self.startScan:
                self.pushCommand("scan on\n")
            self.startScan = datetime.datetime.now() + datetime.timedelta(seconds=SCAN_SECONDS);
            if self.config:
                self.pairing = True
                self.toBePaired = None
                self.pairingNextDevice()

    def pairingNextDevice(self):
        if self.handle and self.pairing and self.config:
            found = self.toBePaired is None
            for aScanner in self.config.AllScanners.elements:
                currScanner = self.config.AllScanners.elements[aScanner]
                if found:
                    self.toBePaired = None
                    if currScanner.there and not currScanner.reader and not currScanner.paired and currScanner.isActive():
                        self.toBePaired = currScanner
                        self.pushCommand("agent on\n")
                        self.pushCommand("default-agent\n")
                        self.pushCommand("pairable on\n")
                        self.pushCommand("pair "+currScanner.id+"\n")
                        print "Pairing "+str(currScanner)
                        break
                else:
                    found = self.toBePaired == currScanner
            self.pairing = not (self.toBePaired is None)

    def connect(self,scanner):
        if self.handle and scanner:
            print "connect "+scanner.id
            self.pushCommand("connect "+scanner.id+"\n")
            scanner.last = datetime.datetime.now()

    def remove(self,scanner):
        if self.handle and scanner and scanner.paired:
            print "remove "+scanner.id
            self.pushCommand("remove "+scanner.id+"\n")
            scanner.last = datetime.datetime.now()

    def connectKey(self,KEY):
        if self.handle:
            if KEY in self.config.AllScanners.elements:
                currScanner = self.config.AllScanners.elements[KEY]
                if currScanner.isActive():
                    self.connect(currScanner)

    def connectMac(self,MAC):
        if self.handle:
            KEY = self.config.AllScanners.makeKey(MAC)
            self.connectKey(KEY)

    def list(self):
        for aScanner in self.config.AllScanners.elements:
            currScanner = self.config.AllScanners.elements[aScanner]
            if currScanner.paired:
                self.screen.draw.text((4,self.screen.linePos+1), str(currScanner.rank)+u"#"+str(currScanner.id)+u": "+currScanner.id, font=self.screen.font,fill=255)
                self.screen.linePos += self.screen.lineHeight

    def pushCommand(self,string):
        #print u"("+string
        self.commandFIFO.append(string)
##        if self.ready and len(self.commandFIFO)==0 :
##            self.writeTrace(string)
##        else:
##            if self.ready:
##                self.writeTrace(self.commandFIFO.pop(0))
            
    def writeTrace(self,string):
        print u"<<"+string
        self.handle.stdin.write(string)
        self.ready = False
            
    def addTodo(self,scanner):
        if scanner in self.todo:
            pass
        else:
            self.todo[scanner] = '!'

    def addDisconnect(self,scanner):
        if self.handle and scanner:
            self.pushCommand("disconnect "+scanner.id+"\n")
            scanner.last = datetime.datetime.now()

    def chooseTodo(self):
        if self.currTodo:
            return
        for scanner in self.todo:
            if scanner == self.toBePaired:
                continue
            self.currTodo = scanner
            #print unicode(scanner)
            self.pushCommand("info "+scanner.id+"\n")
            del self.todo[scanner]
            break

    def control(self):
        self.aQueue = Queue()
        try:
            self.handle = subprocess.Popen(["bluetoothctl","-a"],bufsize=0,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,close_fds=True,cwd=None)
        except:
            traceback.print_exc()
        remove_escape = re.compile(r'(\x98|\x1B\[)[0-?]*[ -\/]*[@-~]')
        remove_spaces = re.compile(r'[ \t]+')
        remove_eols = re.compile(r'\r[\r\n ]+')

        begin = True
        self.ready = False
        self.commandFIFO = []
        while self.handle and self.alive:
            time.sleep(0.1)
            now = datetime.datetime.now()
            if begin:
                begin = False
                self.pushCommand("power on\n")
                self.pushCommand("agent on\n")
                self.pushCommand("default-agent\n")
                self.pushCommand("pairable on\n")
            elif self.startScan and (self.startScan < now):
                self.startScan = None
                self.pushCommand("scan off\n")
                self.pairing = False
                self.toBePaired = None

            try:
                lines = self.aQueue.get(timeout=4.0)
            except Empty,Full:
                self.ready = True
            else:
                try:
                    #print u">>"+unicode(lines)+u"<<"
                    #print u">>"
                    lines = remove_escape.sub(u'',lines)
                    lines = remove_spaces.sub(u' ',lines)
                    lines = remove_eols.sub(u'\r',lines)
                    lines = lines.strip(u" \t\r\n")
                    lines = lines.split(u'\r')
                    while len(lines) >= 1:
                        line = lines.pop(0)
                        line = line.strip(u" \t\n")
                        print u" >"+line+u"<"
                        if line:
                            lineP = line.split(u' ')
                            pref = lineP[0]
                            if pref == u"[bluetooth]#":
                                #if len(lineP) == 1:
                                self.ready = True
                            elif pref == u"Failed":
                                if self.toBePaired:
                                    self.addTodo(self.toBePaired)
                                    self.toBePaired = None
                            elif pref == u"[agent]":
                                if self.toBePaired and (line.find("Enter PIN") > 0):
                                    self.writeTrace(self.toBePaired.fields[u"pin"]+"\n")
                                    self.addTodo(self.toBePaired)
                                    self.toBePaired = None
                            elif len(lineP) > 1 and (lineP[1] == u"Device"):
                                key = self.config.AllScanners.makeKey(lineP[2])
                                if key in self.config.AllScanners.elements:
                                    currScanner = self.config.AllScanners.elements[key]
                                    if pref == u"[NEW]":
                                        currScanner.there = True
                                        if currScanner.isActive():
                                            self.addTodo(currScanner)
                                        else:
                                            self.remove(currScanner)
                                    elif pref == u"[DEL]":
                                        currScanner.there = False
                                    elif pref == u"[CHG]":
                                        currScanner.there = True
                                        if line.find(u"Connected: yes") >= 0:
                                            self.screen.newConnect = True
                                        if currScanner.isActive():
                                            self.addTodo(currScanner)
                                        else:
                                            self.remove(currScanner)
                                        # RSSI: value Connected: yes...
                                    currScanner.last = now
                            elif pref == u"Device":
##Device 00:06:00:04:16:51
##	Name: CT1016405100
##	Alias: CT1016405100
##	Class: 0x400501
##	Paired: no
##	Trusted: no
##	Blocked: no
##	Connected: no
##	LegacyPairing: yes
##	UUID: Human Interface Device... (00001124-0000-1000-8000-00805f9b34fb)
                                key = self.config.AllScanners.makeKey(lineP[1])
                                if key in self.config.AllScanners.elements:
                                    currScanner = self.config.AllScanners.elements[key]
                                    if not currScanner.isActive():
                                        self.remove(currScanner)
                                    else:
                                        if (len(lineP) > 2) and (lineP[2] == u"not"):
                                            currScanner.connected = False
                                            if self.currTodo.id == key:
                                                self.currTodo = None
                                        elif line.find(u"Connected: yes") >= 0:
                                            currScanner.there = True
                                            currScanner.connected = True
                                            self.screen.newConnect = True
                                            self.addTodo(currScanner)
                                        elif self.currTodo.id == key:
                                            pass
                                        else:
                                            if len(lineP) > 1:
                                                self.addTodo(currScanner)
                                            else:
                                                self.currTodo = currScanner
                                    currScanner.last = now
                            elif pref == u"Paired:":
                                self.currTodo.paired = lineP[1] == "yes"
                            elif pref == u"Trusted:":
                                self.currTodo.trusted = lineP[1] == "yes"
                            elif pref == u"Blocked:":
                                self.currTodo.blocked = lineP[1] == "yes"
                            elif pref == u"Connected:":
                                self.currTodo.connected = lineP[1] == "yes"
                            elif pref == u"LegacyPairing:":
                                if not self.currTodo.paired:
                                    self.toBePaired = self.currTodo
                                    if self.currTodo.connected:
                                        self.pushCommand("disconnect "+self.currTodo.id+"\n")
                                    self.pushCommand("scan on\n")
                                    self.pushCommand("trust "+self.currTodo.id+"\n")
                                    self.pushCommand("pair "+self.currTodo.id+"\n")
                                elif not self.currTodo.trusted:                                        
                                    self.pushCommand("trust "+self.currTodo.id+"\n")
                                elif self.currTodo.blocked:                                        
                                    self.pushCommand("unblock "+self.currTodo.id+"\n")
                                elif not self.currTodo.connected:                                        
                                    self.pushCommand("connect "+self.currTodo.id+"\n")
                                self.currTodo.last = datetime.datetime.now()
                                self.currTodo = None
                            else:
                                print "pref="+lineP[0]
                except: # e.g. problems with encoding...
                    traceback.print_exc()                
            if self.ready: #or len(self.todo.keys())>0:
                self.chooseTodo()
                if len(self.commandFIFO):
                    self.writeTrace(self.commandFIFO.pop(0))
##                else:
##                    self.writeTrace(u"\n")

        if self.handle:
            try:
                self.handle.kill()
            except:
                traceback.print_exc()
        self.handle = None

    def enqueue(self):
        while self.handle and self.alive:
            r,w,e = select.select ([self.handle.stdout], [], [], 0)
            if self.handle.stdout in r:
                lines = self.handle.stdout.readline()
                if lines:
                    self.aQueue.put(lines)
            time.sleep(0.1)
    
    def start(self):
        thread = threading.Thread(target=self.control)
        thread.start()
        time.sleep(1.0)
        thread2 = threading.Thread(target=self.enqueue)
        thread2.daemon = True
        thread2.start()
        return thread,thread2
