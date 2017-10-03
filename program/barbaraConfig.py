# -*- coding: utf-8 -*-
#Application configuration (barbara.ini)
import ConfigParser
import sys
import os
import codecs
import traceback
import syslog
import datetime

APPdirectory = "~/akuino/BARBARA"
if sys.argv:
    if len(sys.argv) > 1:
        APPdirectory = sys.argv[1]
APPdirectory = os.path.expanduser(APPdirectory)

class barbaraConfig():

    def cleanString(self,aStr):
        
        if self.crlf:
            aStr = aStr.replace(self.crlf,'\r\n')
        if self.lf:
            aStr = aStr.replace(self.lf,'\n')
        if self.esc:
            aStr = aStr.replace(self.esc,'\x1b')
        
        return aStr

    def __init__(self,hardConfig):
        #Akuino host number is a string of digits
        self.akuinoHost = "".join(aChar for aChar in hardConfig.hostname if aChar.isdigit())
        self.broadcastPort = 1248
        self.broadcastDelay = 10
        self.networkLatency = datetime.timedelta(seconds=30)
        self.applicationPort = 8890
        self.applicationRole = 'a'
        self.alignPrinter = None
        self.printBarcode = None
        self.printListBarcode = None
        self.printDirectory = hardConfig.rundirectory
        self.crlf=None
        self.lf=None
        self.esc=None
        self.braceType=0
	self.braceMin=990000000000
        self.braceMax=999999999999
        self.braceTitle = 'BARBARA'
        self.screenType=0
        self.language = "FR"
        self.defaultAmount = 20.0
        self.omniPIN = 8448

    def load(self):
        global APPdirectory

        aConfig = ConfigParser.RawConfigParser()
        try:
                configFile = os.path.expanduser(APPdirectory+'/barbara.ini')
                aConfig.readfp(codecs.open(configFile,'r','utf8'))
                print(aConfig.sections())
                roleConfig = ""

                if u'network' in aConfig.sections():
                      for anItem in aConfig.items(u'network'):
                        if anItem[1]:
                            key = anItem[0].lower()
                            if key == u'broadcast':
                                try:
                                    self.broadcastPort = int(anItem[1])
                                except:
                                    syslog.syslog(syslog.LOG_ERR, u"BARBARA, port d'annonce invalide: broadcast="+anItem[1])                                
                            elif key == u'delay':
                                try:
                                    self.broadcastDelay = int(anItem[1])
                                except:
                                    syslog.syslog(syslog.LOG_ERR, u"BARBARA, délai entre les annonces invalide: delay="+anItem[1])                                
                            elif key == u'latency':
                                try:
                                    self.networkLatency = datetime.timedelta(seconds=int(anItem[1]))
                                except:
                                    syslog.syslog(syslog.LOG_ERR, u"BARBARA, le décalage permis pour les horloges est invalide: latency="+anItem[1])                                
                            elif key == u'port':
                                try:
                                    self.applicationPort = int(anItem[1])
                                except:
                                    c
                            elif key == u'role':
                                roleConfig = anItem[1]
                                self.applicationRole = anItem[1].lower()
                if u'printer' in aConfig.sections():
                      for anItem in aConfig.items(u'printer'):
                        if anItem[1]:
                            key = anItem[0].lower()
                            if key == u'align':
                                self.alignPrinter = anItem[1]
                            elif key == u'barcode':
                                self.printBarcode = anItem[1]
                            elif key == u'list':
                                self.printListBarcode = anItem[1]
                            elif key == u'directory':
                                self.printDirectory = unicode(anItem[1])
                                print anItem[1]
                                print self.printDirectory
                                try:
                                    if not os.path.exists(self.printDirectory):
                                        print "create"
                                        os.makedirs(self.printDirectory)
                                except:
                                    syslog.syslog(syslog.LOG_ERR, u"BARBARA, problème pour créer: directory="+self.printDirectory)                                
                            elif key == u'crlf':
                                self.crlf = anItem[1]
                            elif key == u'lf':
                                self.lf = anItem[1]
                            elif key == u'esc':
                                self.esc = anItem[1]

                if u'braces' in aConfig.sections():
                      for anItem in aConfig.items(u'braces'):
                        if anItem[1]:
                            key = anItem[0].lower()
                            if key == u'min':
                                try:
                                    self.braceMin = int(anItem[1])
                                    if (self.braceMin < 100000000000) or (self.braceMin > 999999999999):
                                        syslog.syslog(syslog.LOG_ERR, u"BARBARA, bracelet minimum doit être exactement de 12 chiffres: min="+anItem[1])
                                        self.braceMin = 100000000000
                                except:
                                    syslog.syslog(syslog.LOG_ERR, u"BARBARA, bracelet minimum doit être un nombre de 12 chiffres: min="+anItem[1])                                
                            elif key == u'max':
                                try:
                                    self.braceMax = int(anItem[1])
                                    if (self.braceMax < 100000000000) or (self.braceMax > 999999999999):
                                        syslog.syslog(syslog.LOG_ERR, u"BARBARA, bracelet maximum doit être exactement de 12 chiffres: min="+anItem[1])
                                        self.braceMax = 999999999999
                                except:
                                    syslog.syslog(syslog.LOG_ERR, u"BARBARA, bracelet maximum doit être un nombre de 12 chiffres: max="+anItem[1])                                
                            elif key == u'amount':
                                try:
                                    self.defaultAmount = float(anItem[1])
                                    if self.defaultAmount <= 0:
                                        syslog.syslog(syslog.LOG_ERR, u"BARBARA, valeur du bracelet doit etre un nombre comme 20.0   amount="+anItem[1])
                                        self.defaultAmount =20.0
                                except:
                                    syslog.syslog(syslog.LOG_ERR, u"BARBARA, valeur du bracelet doit être un montant en euros. amount="+anItem[1])                                
                            elif key == u'title':
                                self.braceTitle = anItem[1]
                            elif key == u'type':
                                if  anItem[1].lower()== u'rfid':
                                    self.braceType=1
                                else:
                                    self.braceType=0
                            elif key == u'omni':
                                try:
                                    self.omniPIN = int(anItem[1])
                                    if self.omniPIN <= 0:
                                        syslog.syslog(syslog.LOG_ERR, u"Le PIN de l'utilisateur BARBARA doit être nombre supérieur à zéro   omni="+anItem[1])
                                        self.omniPIN =8448
                                except:
                                    syslog.syslog(syslog.LOG_ERR, u"Le PIN de l'utilisateur BARBARA doit être nombre supérieur à zéro   omni="+anItem[1])
                
                if u'screen' in aConfig.sections():
                      for anItem in aConfig.items(u'screen'):
			print anItem
                        if anItem[1]:
                            key = anItem[0].lower()
                            if key == u'type':
                                if anItem[1].lower() == u'touch':
                                    self.screenType=1
                                else:
                                    self.screenType=0

                if self.alignPrinter:
                    self.alignPrinter = self.cleanString(self.alignPrinter)
                if self.printBarcode:
                    self.printBarcode = self.cleanString(self.printBarcode)
                if self.printListBarcode:
                    self.printListBarcode = self.cleanString(self.printListBarcode)
                    
                if self.applicationRole: # a=alone, b,r=binded, remote, c,s=central/server
                    self.applicationRole = self.applicationRole[0]
                    if self.applicationRole == 's':
                        self.applicationRole = 'c'
                    if self.applicationRole == 'r':
                        self.applicationRole = 'b'
                    if self.applicationRole < 'a' or self.applicationRole > 'c':
                        syslog.syslog(syslog.LOG_ERR, u"BARBARA, role "+roleConfig+" doit être autonome, binded ou central")
                        self.applicationRole = 'a';
                else:
                    self.applicationRole = 'a'

                if self.braceMax <= self.braceMin:
                    syslog.syslog(syslog.LOG_ERR, u"BARBARA, Intervalle de génération de bracelets incorrect (max < min): "+unicode(self.braceMax)+" < "+unicode(self.braceMin))
 
                if not self.akuinoHost:
		    self.akuinoHost="local"
                    
        except:
                traceback.print_exc()

