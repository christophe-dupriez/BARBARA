#!/usr/bin/env python
# -*- coding: utf-8 -*-
import unicodecsv
import sets
import time
import threading
import traceback
import datetime
import barcode
import zlib

#### WEB API ####
import web
import jsonpickle

import requests

import barbaraConfig

baseDir = barbaraConfig.APPdirectory+u"/current/"
lastGenerate = 0
EAN = barcode.get_barcode_class('ean13')
        
# Fonction qui transforme les nbres des fichiers CSV en float
def infloat(nbre):
    if nbre:
        try :
            nbre = float(nbre)
        except :
            nbre = nbre.replace(",",".")
            nbre = float(nbre)
    else:
        nbre = 0.0
    return nbre

def digest(aString):
    return ("0000"+unicode(abs(zlib.crc32(aString))))[-4:]

render = web.template.render('templates/',base='layout')

class auto_application_port(web.auto_application):
    def run(self, port=8890, *middleware):
        func = self.wsgifunc(*middleware)
        return web.httpserver.runsimple(func, ('0.0.0.0', port))

app = auto_application_port()

class Configuration(object):
    
    def __init__(self):
        self.barbaraConfig = None
        self.barcode = {}
        self.AllUsers = AllUsers(self)
        self.AllBraces = AllBraces(self)
        self.AllProducts = AllProducts(self)
        self.AllQty = AllQty(self)
        self.AllScanners = AllScanners(self)
        self.AllMessages = AllMessages(self)
        self.AllTransactions = AllTransactions(self)
        self.app = None #web application to serve API

    def load_local(self):
        self.AllMessages.load_local()
        self.AllQty.load_local()

    def load_remote(self):
        if self.barbaraConfig.applicationRole == u'b':
            self.AllUsers.load_remote()
            #self.AllBraces.load_remote()
            self.AllBraces.local = False
            self.AllProducts.load_remote()
            self.AllScanners.load_remote()
            self.AllTransactions.load_remote()
        else:
            self.AllUsers.load_local()
            #self.AllBraces.load_local()
            self.AllBraces.local = True
            self.AllProducts.load_local()
            self.AllScanners.load_local()
            self.AllTransactions.load_local()

    def startWebAPI(self):
        global app
        app.run(port=self.barbaraConfig.applicationPort)

    def findAll(self,anObject):
        if isInstance(anObject,User):
            return self.AllUsers
        elif isInstance(anObject,Products):
            return self.AllProducts
        elif isInstance(anObject,Braces):
            return self.AllBraces
        elif isInstance(anObject,Scanner):
            return self.AllScanners
        elif isInstance(anObject,Message):
            return self.AllMessages
        elif isInstance(anObject,Qty):
            return self.AllQty
        else:
            return None

    def findAllFromName(self,className):
        if className == u"Configuration.User":
            return self.AllUsers
        elif className == u"Configuration.Products":
            return self.AllProducts
        elif className == u"Configuration.Braces":
            return self.AllBraces
        elif className == u"Configuration.Scanner":
            return self.AllScanners
        elif className == u"Configuration.Message":
            return self.AllMessages
        elif className == u"Configuration.Qty":
            return self.AllQty
        else:
            return None

    def findAllFromObject(self,anObject):
        className = anObject.__class__.__name__
        if className == u"User":
            return self.AllUsers
        elif className == u"Products":
            return self.AllProducts
        elif className == u"Braces":
            return self.AllBraces
        elif className == u"Scanner":
            return self.AllScanners
        elif className == u"Message":
            return self.AllMessages
        elif className == u"Qty":
            return self.AllQty
        else:
            return None

    def storeObject(self,data):
        aType = data[u'py/object']
        if aType:
            typeList = aType.split('.')
            aTypeName = typeList[len(typeList)-1]
            aClass = globals()[aTypeName]
            if aClass:
                theId = data[u'id']
                if theId:
                    allObjects = self.findAllFromName(aType)
                    if theId in allObjects.elements:
                        theObject = allObjects.elements[theId]
                    else:
                        theObject = aClass()
                        allObjects.elements[theId] = theObject
                        theObject.id = theId
                        if u"barcode" in data:
                            self.barcode[theId] = theObject
                    for aField in data:
                        print (aField+u"="+str(data[aField]))
                        if aField != u'id' and aField != u'py/object':
                            setattr(theObject,aField,data[aField])
                    print aTypeName+u"/"+theId+u" stored"
#        for aField in someFields:
                    return theObject
                else:
                    print str(data)+u": no id?"          
            else:
                print aTypeName+u": class unknown"                
        else:
            print str(data)+u": no py/object?"          
        return None
                
    
    #### WEB client API ####
    def client_BarcodeObject(self,barCode):
        response = requests.get(self.barbaraConfig.applicationURL+u'/barcode/'+str(barCode))

        if response.status_code == 200:
            try:
                data = response.json()
                if data:
                    return self.storeObject(data)
            except:
                traceback.print_exc()
                return None
        else:
            print u"Get barcode "+barcode+u" HTTP error="+unicode(response.status_code)
        return None

    def ensureBarcode(self,res):
        if res in self.barcode:
            barcodeObject = self.barcode[res]
            allObjects = self.findAllFromObject(barcodeObject)
            if allObjects.local:
                return barcodeObject
            else:
                return self.client_BarcodeObject(res)
        else: # No way to know if a barcode is local or remote without querying the central !
            if self.barbaraConfig.applicationRole == u'b':
                return self.client_BarcodeObject(res)
            return None

    def client_GetObject(self,allObjects,key):
        response = requests.get(self.barbaraConfig.applicationURL+u"/"+allObjects.id+u"/"+key)

        if response.status_code == 200:
            try:
                data = response.json()
                if data:
                    return self.storeObject(data)
            except:
                traceback.print_exc()
                return None
        else:
            print u"Get object "+key+u" HTTP error="+unicode(response.status_code)
        return None

    def client_SaveObjectFields(self,anObject,allObjects):
        to_protect = jsonpickle.encode(anObject.fields)
        protect_crc = zlib.crc32(str(anObject.id)+u"/"+to_protect)
        response = requests.post(self.barbaraConfig.applicationURL+u'/save/'+allObjects.id+u'/'+str(anObject.id)+u"/"+unicode(protect_crc), data=to_protect)

        if response.status_code == 200:
            try:
                data = response.json()
                if data:
                    return data[u'fields']
            except:
                traceback.print_exc()
                return None
        else:
            print "Save object HTTP error="+unicode(response.status_code)
        return None

    def client_ReserveBrace(self,forUser):#TODO PAS JUSTE!!!
        response = requests.get(self.barbaraConfig.applicationURL+ ( Configuration.reserve_user.path if forUser else Configuration.reserve_brace.path ) )

        if response.status_code == 200:
            try:
                data = response.json()
                if data:
                    return self.storeObject(data)
            except:
                traceback.print_exc()
                return None
        else:
            print "Reserve Brace HTTP error="+unicode(response.status_code)
        return None

    def client_CreditBrace(self,userid,barcode,amount):
        to_protect = userid+u'/'+barcode+u'/'+unicode(amount)
        protect_crc = zlib.crc32(to_protect)
        response = requests.get(self.barbaraConfig.applicationURL+u'/brace/credit/'+to_protect+u"/"+unicode(protect_crc))

        print u"Request status="+unicode(response.status_code)
        if response.status_code == 200:
            try:
                data = response.json()
                if data:
                    print("data="+unicode(data))
                    return self.storeObject(data)
                else:
                    print("no data?")
            except:
                traceback.print_exc()
        else:
            print u"Request status="+unicode(response.status_code)
            traceback.print_exc()
        return None

    def client_BuyWithBrace(self,userid,barcode,amount,panier):
        basket = u""
        for aProduct in panier:
            basket += aProduct.id+u"*"+unicode(panier[aProduct])+u";"
        to_protect = userid+u'/'+barcode+u'/'+unicode(amount)+u"/"+basket
        protect_crc = zlib.crc32(to_protect)
        response = requests.get(self.barbaraConfig.applicationURL+u'/brace/buy/'+to_protect+u"/"+unicode(protect_crc))

        if response.status_code == 200:
            try:
                data = response.json()
                if data:
                    return self.storeObject(data)
            except:
                traceback.print_exc()
                return None
        else:
            print "Buy using a Brace HTTP error="+unicode(response.status_code)
        return None

    def htmlNow(self):
        return datetime.datetime.now().strftime("%Y/%m/%d %H:%M")

class ConfigurationObject(object):

    def __init__(self):
        self.fields = {}
        self.id = None

    def name(self,configuration):
        return configuration.barbaraConfig.braceTitle

    def refreshed(self,configuration):
        if configuration.barbaraConfig.applicationRole == u'b':
            allObjects = configuration.findAllFromObject(self)
            if allObjects.local:
                return self
            else:
                return configuration.client_BarcodeObject(self.id)
        else:
            return self

    def save(self,configuration,anUser=""):
        self.fields["time"] = unicode(datetime.datetime.now())
        self.fields["user"] = anUser.id
        allObjects = configuration.findAllFromObject(self)
        if allObjects.local:
            print allObjects.filename
            print allObjects.fieldnames
            with open(baseDir+allObjects.filename,"a") as csvfile:
                writer = unicodecsv.DictWriter(csvfile, delimiter = '\t', fieldnames=allObjects.fieldnames, encoding="utf-8")
                writer.writerow(self.fields)
        else:
            configuration.client_SaveObjectFields(self,allObjects)
        return self

    def strActive(self):
        if self.isActive():
            return "OK"
        else:
            return "nok"

    def htmlBarcode(self):
        try:
            if len(self.id) <= 13 :
                aBarcode = EAN(unicode(self.id),writer=barcode.writer.ImageWriter())
            else:  # On pourrait utiliser le Code128...
                return None
        except:
            return None
        aBarcode.save('/run/akuino/'+unicode(self.id))
        return '/static/run/akuino/'+unicode(self.id)+'.png'

class AllObjects(object):

    def __init__(self,config):
        self.ids = self.id + u"s"
        self.filename = self.ids + u".csv"
        self.local = False # remote by default...
        self.config = config
        self.keyColumn = u"barcode"
        self.elements = {}

    def ensure_fileReader(self): # returns a file and a reader if OK, None if error
        try: #si le fichier existe
            csvfile = open(baseDir+self.filename)
            return csvfile, unicodecsv.DictReader(csvfile, delimiter = '\t', encoding=u"utf-8") #, fieldnames=self.fieldnames)
        except: #si le fichier n'existe pas
            try:
                with open(baseDir+self.filename, u'w') as csvfile:
                    writer = unicodecsv.DictWriter(csvfile, fieldnames=self.fieldnames, delimiter = '\t', encoding=u"utf-8")
                    writer.writeheader()
                csvfile = open(baseDir+self.filename)
                return unicodecsvfile, csv.DictReader(csvfile, delimiter = '\t', encoding=u"utf-8") #, fieldnames=self.fieldnames)
            except:
                traceback.print_exc()
                return None, None

    def load_local(self):
        self.local = True
        csvfile, reader = self.ensure_fileReader()
        if csvfile:
            try:
                for row in reader:
                    if self.keyColumn in row:
                        key = row[self.keyColumn]
                        if key:
                            self.assignObject(key,row)
                    else:
                           print unicode(row) + u" : NO column "+self.keyColumn+u" in "+unicode(row.keys())
            except:
                print u"Error reading CSV "+baseDir+self.filename
                traceback.print_exc()
            try:
                csvfile.close()
            except:
                traceback.print_exc()
        else:
            print u"Can't open file "+baseDir+self.filename+" as CSV"
                    
    def load_remote(self):
        if self.config.barbaraConfig.applicationRole == u'b':
            #Loading is deferred to actual need to read an object...
            pass
        else:
            self.load_local()
                    
    def newObject(self):
        return None

    def defaultRow(self,key):
        return None

    def createObject(self,key,row):
        currObject = self.newObject()
        currObject.fields = row
        currObject.id = key
        self.elements[key] = currObject
        if u'barcode' in row:
            barkey = row[u'barcode']
            if barkey:
                if barkey not in self.config.barcode:
                    self.config.barcode[barkey] = currObject
                else:
                    print u"Error : "+unicode(barkey)+u" already used by "+unicode(self.config.barcode[barkey])
            else:
                print u"Error : key is null"
        return currObject

    def assignObject(self,key,row):
        currObject = None
        if key in self.elements:
            currObject = self.elements[key]
            if row != None:
                currObject.fields = row
        elif key in self.config.barcode: # assigned to another type: NO NO !
            print u"Error : "+unicode(key)+u" already used by "+unicode(self.config.barcode[key])
        else:
            if row == None:
                row = self.defaultRow(key)
            currObject = self.createObject(key,row)
        return currObject
        
    def elements_refreshed(self):
        if not self.local:
            response = requests.get(self.config.barbaraConfig.applicationURL+u'/'+self.ids+u'/list')

            if response.status_code == 200:
                try:
                    data = response.json()
                    if data:
                        for barkey in data:
                            self.assignObject(barkey,None)
                            self.refresh(barkey)
                except:
                    traceback.print_exc()
                traceback.print_exc()
            else:
                print "Elements refresh HTTP error="+unicode(response.status_code)
        return self.elements

    def refresh(self,id):
        obj = self.elements[id]
        if obj == None:
            return None
        return obj.refreshed(self.config)

    def generateBarcode(self):
        global lastGenerate
        
        if not self.local:
            response = requests.get(self.config.barbaraConfig.applicationURL+u'/'+self.ids+u'/generate')

            if response.status_code == 200:
                try:
                    data = response.json()
                    if data:
                        obj = self.config.storeObject(data)
                        return obj
                except:
                    traceback.print_exc()
                    return None
            else:
                print "Generate HTTP error="+unicode(esponse.status_code)
                return None

        else:
            if not lastGenerate:
                lastGenerate = self.config.barbaraConfig.braceMin-1

            i = lastGenerate+1
            while i <= self.config.barbaraConfig.braceMax:
                aBarcode = EAN(unicode(i))
                barkey = aBarcode.get_fullcode()
                if barkey in self.config.barcode:
                    i += 1
                else:
                    lastGenerate = i
                    return self.createObject(barkey,self.defaultRow(barkey))
            lastGenerate = self.config.barbaraConfig.braceMax
            return None
        
    def countActive(self):
        count = 0
        for key in self.elements:
            if self.elements[key].isActive():
                count += 1
        return count
        
class AllTransactions(AllObjects):

    def __init__(self, config):
        self.id = u"transaction"
        AllObjects.__init__(self,config)
        self.filename = u"transac.csv"
        self.total_credit = 0.0
        self.total_buyWithBrace = 0.0
        self.total_bottles = 0
        self.fieldnames = ["time","type","brace","amount","product","qty","user"]

    def newObject(self):
        return Transaction()

    def defaultRow(self,key):
        return {"time":unicode(datetime.datetime.now()),"type":"","brace":"","amount":"0.0","product":"","qty":"","user":""}

    def load_local(self):
        self.local = True
        csvfile, reader = self.ensure_fileReader()
        if csvfile:
            try:
                self.total_credit = 0.0
                self.total_buyWithBrace = 0.0
                self.total_bottles = 0
                for row in reader:
                    aUser = None
                    amount = infloat(row[u"amount"])
                    qty = infloat(row[u"qty"])
                    barkey = row[u"user"]
                    if barkey:
                        aUser = self.config.AllUsers.assignObject(barkey,None)
                    aBrace = None
                    barkey = row[u"brace"]
                    if barkey:
                        aBrace = self.config.AllBraces.assignObject(barkey,None)
                    aProduct = None
                    barkey = row[u"product"]
                    if barkey:
                        aProduct = self.config.AllProducts.assignObject(barkey, { u"barcode":barkey,"name":"product#"+barkey,"price":unicode(amount/qty),"qty":"" } )

                    if row[u"type"] == u"C": #Credit or Debit of a Brace
                        if aBrace:
                            self.load_credit(aUser,aBrace,amount)
                            self.total_credit = self.total_credit+amount
                    elif row[u"type"] == u"B": #Buy(remit) with a Brace some product or service
                        if aBrace:
                            self.load_buyWithBrace(aUser,aBrace,amount,None)
                            self.total_buyWithBrace = self.total_buyWithBrace+amount
                    elif row[u"type"] == u"S": #Sale of a product or service (stock debit)
                        if aProduct:
                            aProduct.sell(qty)
                            self.total_bottles = self.total_bottles+qty
            except:
                traceback.print_exc()
            try:
                csvfile.close()
            except:
                traceback.print_exc()

    def load_credit(self,aUser,aBrace,amount):
            # Marque le bracelet comme vendu
            aBrace.fields[u"sold"] = u"yes"
            if aBrace.fields[u"amount"]:
                aBrace.fields[u"amount"] = unicode(infloat(aBrace.fields[u"amount"])+amount)
            else:
                aBrace.fields[u"amount"] = unicode(amount)
        
    def load_buyWithBrace(self,aUser,aBrace,total,basket):
            solde = aBrace.fields[u"amount"] #acquisition du solde du bracelet
            solde = infloat(solde)
            reste = solde - total
            
            aBrace.fields[u"amount"] = unicode(reste)

            if basket:
                for productId in basket:
                    if productId and productId in self.config.AllProducts.elements:
                        aProduct = self.config.AllProducts.elements[productId]
                        aProduct.sell(infloat(basket[productId]))

    def credit(self,aUser,aBrace,amount):
            self.load_credit(aUser,aBrace,amount)
            Transaction().make_credit(self.config,aUser,aBrace,amount)
            self.total_credit = self.total_credit + amount
        
    def buyWithBrace(self,aUser,aBrace,total,basket):
            self.load_buyWithBrace(aUser,aBrace,total,basket)
            Transaction().make_buyWithBrace(self.config,aUser,aBrace,total)
            self.total_buyWithBrace = self.total_buyWithBrace + float(total)

            if basket:
                for aProduct in basket:
                    Transaction().make_sell(self.config,aUser,aBrace,aProduct,infloat(basket[aProduct]))
                    self.total_bottles = self.total_bottles+infloat(basket[aProduct])

class Transaction (ConfigurationObject):

    def __repr__(self):
        string = unicode(self.id) + u" " + unicode(self.fields[u'type']) + self.fields[u'time'] + self.fields[u'brace'] + self.fields[u'amount'] +self.fields[u'basket']
        return string

    def __str__(self):
        string = u"\nTransaction:"
        for field in self.fields:
            string = string + u"\n" + field + u" : " + self.fields[field]
        return string + u"\n"

    def save(self,config): #time,type,brace,amount,product,qty,user
        with open(baseDir+config.AllTransactions.filename,"a") as csvfile:
            writer = unicodecsv.DictWriter(csvfile, delimiter = '\t', fieldnames=config.AllTransactions.fieldnames, encoding="utf-8")
            writer.writerow(self.fields)
            print unicode(self.fields)

    def make_buyWithBrace(self,config,aUser,aBrace,amount):
        self.fields = { u"time":unicode(datetime.datetime.now()), u"type":"B", u"user":aUser.id, u"brace":aBrace.id, u"amount":unicode(amount), u"product":"", u"qty":"" }
        self.save(config)

    def make_credit(self,config,aUser,aBrace,amount):
        self.fields = { u"time":unicode(datetime.datetime.now()), u"type":"C", u"user":aUser.id, u"brace":aBrace.id, u"amount":unicode(amount), u"product":"", u"qty":"" }
        self.save(config)

    def make_sell(self,config,aUser,aBrace,aProduct,qty):
        self.fields = { u"time":unicode(datetime.datetime.now()), u"type":"S", u"user":aUser.id, u"brace":aBrace.id, u"amount":unicode(infloat(aProduct.fields[u"price"])*qty), u"product":aProduct.id, u"qty":unicode(qty) }
        self.save(config)

class AllUsers(AllObjects):

    def __init__(self, config):
        self.id = u"user"
        AllObjects.__init__(self,config)
        self.fieldnames = ["time",'language','name','barcode','access',"user"]

    def newObject(self):
        return User()

    def defaultRow(self,key):
        return {"time":unicode(datetime.datetime.now()),'language':'FR','name':"",'barcode':key,'access':'A',"user":""}

class AllProducts(AllObjects):

    def __init__(self, config):
        self.id = u"product"
        AllObjects.__init__(self,config)
        self.fieldnames = ["time","name","barcode","price","qty","deny","user"]

    def newObject(self):
        return Products()

    def defaultRow(self,key):
        return {"time":unicode(datetime.datetime.now()),"name":"","barcode":key,"price":"0.0","qty":"","deny":"","user":""}

class AllBraces(AllObjects):

    def __init__(self, config):
        self.id = u"brace"
        AllObjects.__init__(self,config)
        self.fieldnames = ["time","barcode","amount","sold","user"]

    def newObject(self):
        return Braces()

    def defaultRow(self,key):
        return {"time":unicode(datetime.datetime.now()),"barcode":key,"amount":"0.0","sold":"no","user":""}

class AllQty(AllObjects):

    def __init__(self, config):
        self.id = u"number"
        AllObjects.__init__(self,config)
        self.fieldnames = [u'barcode','number']

    def newObject(self):
        return Qty()

    def defaultRow(self,key):
        return {"barcode":key,"number":""}

class AllMessages(AllObjects):

    def __init__(self, config):
        self.id = u"message"
        AllObjects.__init__(self,config)
        self.fieldnames = ["barcode","EN","FR","NL","DE","LU"]

    def newObject(self):
        return Message()

    def defaultRow(self,key):
        return {"barcode":key,"EN":"","FR":"","NL":"","DE":"","LU":""}

class AllScanners(AllObjects):

    def __init__(self, config):
        self.id = u"scanner"
        AllObjects.__init__(self,config)
        self.keyColumn = u"mac"
        self.fieldnames = ["time","mac","pin","client","name","user"]

    def makeKey(self, MAC):
        return MAC.upper()

    def defaultName(self, MAC):
        return digest(self.makeKey(MAC))

    def load_local(self):
        self.local = True
        csvfile, reader = self.ensure_fileReader()
        if csvfile:
            try:
                for row in reader:
                    mac = None
                    if u'mac' in row:
                        mac = row[u'mac'].upper()
                    currObject = self.newObject()
                    currObject.fields = row
                    currObject.id = mac
                    if u'name' in row and row[u'name']:
                        pass
                    else:
                        currObject.fields[u'name'] = self.defaultName(mac)                        
                    self.elements[mac] = currObject
            except:
                traceback.print_exc()
            try:
                csvfile.close()
            except:
                traceback.print_exc()

    def load_remote(self):
        self.local = False
        response = requests.get(self.config.barbaraConfig.applicationURL+u'/scanners/list')

        if response.status_code == 200:
            try:
                data = response.json()
                if data:
                    for MACkey in data:
                        currObject = self.newObject()
                        currObject.id = MACkey
                        self.elements[MACkey] = currObject
                        self.config.client_GetObject(self,MACkey)
                        currObject.there = False
                        currObject.paired = False
                        currObject.trusted = False
                        currObject.blocked = False
                        currObject.connected = False
                        currObject.last = None
                        currObject.reader = None                        
            except:
                traceback.print_exc()
        else:
            print "Load remote HTTP error="+unicode(response.status_code)

    def newObject(self):
        return Scanner()

    def defaultRow(self,key): #PIN par defaut selon la marque choisie!
        return {"time":unicode(datetime.datetime.now()),"mac":key,"pin":"10010","client":"1","name":digest(key),"user":""}

class User(ConfigurationObject):

    def __repr__(self):
        string = self.id + u" " + self.fields[u'users']
        return string

    def __str__(self):
        string = u"\nUtilisateur:"
        for field in self.fields:
            string = string + u"\n" + field + u" : " + self.fields[field]
        return string + u"\n"

    def name(self,configuration):
        return (("Collab."+self.fields[u"name"]) if self.fields[u"name"] else u"COLLAB") + ( ("/"+self.fields[u"access"]) if self.fields[u"access"] else u"")

    def access(self):
        if not self.fields:
            return u'n' # undefined user
        elif not u'access' in self.fields:
            return u'a' # No access column content = all rights but no management
        else:
            acc = self.fields[u'access']
            if not acc:
                return u'n' # Access column empty = no rights
            acc = acc.strip()
            if not acc:
                return u'n' # Access column empty = no rights
            return acc[0].lower()
        
    def getAccessCode(self):
        acc = self.access()
        if acc == u'n':
            return 0
        elif acc == u'g':
            return 921
        elif acc == u'a':
            return 21
        elif acc == u'b':
            return 1
        elif acc == u'c':
            return 20
        else:
            return 0
        
    def setAccessCode(self,code):
        sCode = unicode(code)
        self.fields[u'access'] = u''
        if u"9" in sCode:
            self.fields[u'access'] = u'g'
        else:
            if u"2" in sCode:
                if u"1" in sCode:
                    self.fields[u'access'] = u'a'
                else:
                    self.fields[u'access'] = u'c'
            else:
                if u"1" in sCode:
                    self.fields[u'access'] = u'b'

    def allowed(self,mode): # mode = C=consommation,B=bracelet,A=C+B, G=Config, N=None
        acc = self.access()
        print("authorise "+acc+u" for "+mode+u"?")
        if mode == acc:
            return True
        if acc == u'a' or acc == u'g':
            return mode == u'b' or mode == u'c'
        return False

    def setInactive(self): # mode = C=consommation,B=bracelet,A=C+B, G=Config, N=None
        self.fields[u'access'] = u'n'

    def isActive(self): # mode = C=consommation,B=bracelet,A=C+B, G=Config, N=None
        acc = self.access()
        return acc != 'n'

class Products(ConfigurationObject):

    def __repr__(self):
        string = self.id + u" " + self.fields[u'name']
        return string

    def __str__(self):
        string = u"\nProduit:"
        for field in self.fields:
            string = string + u"\n" + field + u" : " + self.fields[field]
        return string + u"\n"

    def name(self,configuration):
        return ("Prod."+ (self.fields[u"name"]) if self.fields[u"name"] else u"PRODUIT") + ( ("/"+self.fields[u"amount"]) if self.fields[u"amount"] else u"")

    def sell(self,sale):
        self.fields[u"qty"] = unicode(infloat(self.fields[u"qty"])+sale)

    def getCents(self):
        return int(infloat(self.fields[u"price"])*100.0)

    def setCents(self,cents):
        self.fields[u"price"] = unicode(cents/100.0)

    def setInactive(self):
        self.fields[u'deny'] = u'1'

    def isActive(self):
        if not u"deny" in self.fields:
            return True
        denial = self.fields[u"deny"]
        if denial:
            denial = denial[0].lower()
        return not (denial and (denial in ['o','y','+','1','2','3','4','5','6','7','8','9']) )

class Braces(ConfigurationObject):

    def __repr__(self):
        string = self.id + u" " + self.fields[u'brace']
        return string

    def __str__(self):
        string = u"\nBracelet:"
        for field in self.fields:
            string = string + u"\n" + field + u" : " + self.fields[field]
        return string + u"\n"

    def setInactive(self):
        self.fields[u'amount'] = u''

    def isActive(self):
        return self.fields[u"amount"]

class Qty(ConfigurationObject):

    def __repr__(self):
        string = self.id + u" " + self.fields[u'number']
        return string

    def __str__(self):
        string = u"\nNombre:"
        for field in self.fields:
            string = string + u"\n" + field + u" : " + self.fields[field]
        return string + u"\n"
    
    def name(self,configuration):
        return u"Num."+ self.id

class Message(ConfigurationObject):

    def __repr__(self):
        string = u""
        string = string + self.fields[u'acronym']
        return string

    def __str__(self):
        string = u"\nMessage:"
        for field in self.fields:
            string = string + u"\n" + field + u" : " + self.fields[field]
        return string + u"\n"

    def name(self,configuration):
        return u"Mess."+ self.id

### Configuration Singleton ###
c = Configuration()

class Scanner(ConfigurationObject):
    id = None
    key = None
    there = False
    paired = False
    trusted = False
    blocked = False
    connected = False
    last = None
    reader = None

    def __repr__(self):
        string = u"#"+str(self.id) + u"=" + self.fields[u'name']
        return string

    def __str__(self):
        string = u"\nScanner #"+str(self.id)
        for field in self.fields:
            if self.fields[field]:
                string = string + u"\n" + field + u" : " + self.fields[field]
        return string + u"\n"

    def name(self,configuration):
        return u"Scan." + self.fields[u'name']

    def setInactive(self):
        self.fields[u'client'] = u'2'

    def isActive(self):

        global c

        client = self.fields[u"client"]
        if self.id == "AFANDBARCODE":
            if client and (len(client) > 1):
                client = c.barbaraConfig.akuinoHost
                self.fields[u'client'] = client

##        if denial:
##            denial = denial[0].lower()
##        return not (denial and (denial in ['o','y','+','1','2','3','4','5','6','7','8','9']) )
        return client and client == c.barbaraConfig.akuinoHost

    def strActive(self):
        if self.isActive():
            return "OK"
        else:
            denial = self.fields[u"client"]
            if denial == "2":
                return "new"
            else:
                return "nok"

#### WEB server API ####
class ListConfigurationObject(app.page):
    allObjects = c.AllUsers
    path = u'/'+allObjects.ids+u'/list'
        
    def GET(self):
        print self.allObjects.ids+" "+self.path
        web.header('Content-Type', u'application/json;charset=utf-8')
        return jsonpickle.encode(self.allObjects.elements.keys())
##        output = self.classNames+u':['
##        for key in self.allObjects.elements:
##                output += str(key) + u','
##        output += u']';
##        return output

class GetConfigurationObject(app.page):
    allObjects = c.AllUsers
    path = u'/'+allObjects.id+u'/(.*)'

    def GET(self, objectId):
        print self.allObjects.ids+" "+self.path
        web.header('Content-Type', u'application/json;charset=utf-8')
        if objectId in self.allObjects.elements:
            return jsonpickle.encode(self.allObjects.elements[objectId])
        else:
            return u""

class SaveConfigurationObject(app.page):
    allObjects = c.AllUsers
    path = u'/save/'+allObjects.id+u'/(.*)/(.*)'

    def POST(self, objectId, checksum):
        web.header('Content-Type', u'application/json')
        protect_crc = zlib.crc32(objectId+u"/"+web.data())
        if checksum != unicode(protect_crc):
            return u""
        fieldsReceived = None
        try:
            fieldsReceived = jsonpickle.decode(web.data())
            currObject = self.allObjects.assignObject(objectId,fieldsReceived)
            if currObject.__class__.__name__ in ["User","Products"]:
                allObjects = configuration.findAllFromObject(currObject)
                if allObjects.local:
                    with open(baseDir+config.allObjects.filename,"a") as csvfile:
                        writer = unicodecsv.DictWriter(csvfile, delimiter = '\t', fieldnames=config.allObjects.fieldnames, encoding="utf-8")
                        writer.writerow(self.fields)
        except:
            traceback.print_exc()
        return fieldsReceived

class GenerateConfigurationObject(app.page):
    allObjects = c.AllUsers
    path = u'/'+allObjects.ids+u'/generate'

    def GET(self):
        web.header('Content-Type', u'application/json;charset=utf-8')
        generated = self.allObjects.generateBarcode()
        if generated:
            return jsonpickle.encode(generated)
        else:
            return u""

class getBarcodeObject(app.page):
    path = u'/barcode/(.*)'
    allObjects = c.barcode

    def GET(self, objectId):
        web.header('Content-Type', u'application/json;charset=utf-8')
        if objectId in self.allObjects:
            return jsonpickle.encode(getBarcodeObject.allObjects[objectId])
        else:
            return u""

class list_users(ListConfigurationObject):
    allObjects = c.AllUsers
    path = u'/users/list'
    
class get_user(GetConfigurationObject):
    allObjects = c.AllUsers
    
class generate_user(GenerateConfigurationObject):
    allObjects = c.AllUsers
    path = u'/users/generate'
    
class save_user(SaveConfigurationObject):
    allObjects = c.AllUsers
    path = u'/save/user/(.*)/(.*)'
    
class print_users(app.page):
    path = u'/users/print'

    def GET(self):
        web.header('Content-Type', u'text/html;charset=utf-8')
        return render.users_print(c)
    
# Ajoute l'argent au bracelet
class credit_brace(app.page):
    path = u'/brace/credit/(.*)/(.*)/(.*)/(.*)'

    def GET(self, userId, braceId, amount, checksum):
        web.header('Content-Type', u'application/json;charset=utf-8')
        protect_crc = zlib.crc32(userId+u"/"+braceId+u"/"+amount)
        if checksum != unicode(protect_crc):
            print(checksum+u": checksum should be "+unicode(protect_crc))
            return u""
        if userId and userId in c.AllUsers.elements:
            try:
                aUser =  c.AllUsers.elements[userId]
                amount = infloat(amount)
                if not braceId in c.AllBraces.elements:
                    print(braceId+u": brace does not exist?")
                    aRow = c.AllBraces.defaultRow(braceId)
                    aRow['sold'] = u"yes"
                    aBrace = c.AllBraces.assignObject(braceId,aRow)
                else:
                    aBrace = c.AllBraces.elements[braceId]
                c.AllTransactions.credit(aUser,aBrace,amount)
                return jsonpickle.encode(aBrace)
            except:
                print(braceId+u"+u"+unicode(amount))
                traceback.print_exc()
        else:
            print(userId+u": user does not exist?")
        return u""

# Debiter un bracelet (achat)
class buy_withbrace(app.page):
    path = u'/brace/buy/(.*)/(.*)/(.*)/(.*)/(.*)'

    def GET(self, userId, braceId, amount,basket, checksum):
        web.header('Content-Type', u'application/json;charset=utf-8')
        protect_crc = zlib.crc32(userId+u"/"+braceId+u"/"+amount+u"/"+basket)
        if checksum != unicode(protect_crc):
            return u""
        if userId and userId in c.AllUsers.elements:
            try:
                aUser =  c.AllUsers.elements[userId]
                amount = infloat(amount)
                basketLines = basket.split(";")
                if braceId in c.AllBraces.elements:
                    aBrace = c.AllBraces.elements[braceId]
                    if not aBrace.fields[u"amount"]:
                        return u""
                    solde = infloat(aBrace.fields[u"amount"])
                    if solde < amount:
                        return u""

                    basketDic = {}
                    for line in basketLines:
                        if line:
                            productData = line.split('*')
                            if productData[0] in c.AllProducts.elements:
                                aProduct = c.AllProducts.elements[productData[0]]
                                basketDic[aProduct] = productData[1]
                            else:
                                print productData[0]+u" is not known as a Product"
                    c.AllTransactions.buyWithBrace(aUser,aBrace,amount,basketDic)

                    return jsonpickle.encode(aBrace)
                else:
                    print(braceId+u" does not exist?")
            except:
                print(braceId+u"+u"+unicode(amount))
                traceback.print_exc()
        return u""

class list_braces(ListConfigurationObject):
    allObjects = c.AllBraces
    path = u'/braces/list'
    
    
class print_braces_code(app.page):
    path = u'/braces/printcode'

    def GET(self):
        web.header('Content-Type', u'text/html;charset=utf-8')
        return render.braces_printcode(c)

class print_braces(app.page):
    path = u'/braces/print'

    def GET(self):
        web.header('Content-Type', u'text/html;charset=utf-8')
        return render.braces_print(c)

##    def GET(self):
##        web.header('Content-Type', u'text/html;charset=utf-8')
##        result = datetime.datetime.now().strftime("%Y/%m/%d %H:%M BRACES")  #affichage de la date et de l'heure
##        total = 0.0
##        for key in c.AllBraces.elements.keys():
##            try:
##                amount = c.AllBraces.elements[key].fields[u"amount"]
##                amount = infloat(amount)
##                if amount != 0.0:
##                    result+=u"<br/>"+unicode(key)+u" = "+unicode(amount)
##                    total += amount
##            except:
##                print (key+u" not printed.")
##                pass
##        result += u"<br/><br/>Total = "+unicode(total)
##        return result
    
class get_brace(GetConfigurationObject):
    allObjects = c.AllBraces
    
class save_brace(SaveConfigurationObject):
    allObjects = c.AllBraces
    path = u'/save/brace/(.*)/(.*)'
    
class generate_brace(GenerateConfigurationObject):
    allObjects = c.AllBraces
    path = u'/braces/generate'
    
class list_products(ListConfigurationObject):
    allObjects = c.AllProducts
    path = u'/products/list'
    
class print_products(app.page):
    path = u'/products/print'

    def GET(self):
        web.header('Content-Type', u'text/html;charset=utf-8')
        return render.products_print(c)

##    def GET(self):
##        web.header('Content-Type', u'text/html;charset=utf-8')
##        result = datetime.datetime.now().strftime("%Y/%m/%d %H:%M CATALOGUE")  #affichage de la date et de l'heure
##        total = 0.0
##        for key in c.AllProducts.elements.keys():
##            result+=u"<br/>"+unicode(key)
##            try:
##                currProdFields = c.AllProducts.elements[key].fields
##                name = currProdFields[u"name"]
##                if name:
##                    result += u": "+name
##                amount = currProdFields[u"price"]
##                amount = infloat(amount)
##                if amount != 0.0:
##                    result += u" : "+unicode(amount) + u"€"
##                qty = currProdFields[u"qty"]
##                qty = infloat(qty)
##                if qty != 0.0:
##                    result += u" x "+unicode(qty)
##                    if amount != 0.0:
##                        prod_total = qty*amount
##                        result += u" = "+unicode(prod_total) + u"€"
##                        total += prod_total
##            except:
##                print (key+u" not printed.")
##                pass
##        result += u"<br/><br/>Total = "+unicode(total)+u"€"
##        return result
    
class get_product(GetConfigurationObject):
    allObjects = c.AllProducts

class save_product(SaveConfigurationObject):
    allObjects = c.AllProducts
    path = u'/save/product/(.*)/(.*)'
    
class generate_product(GenerateConfigurationObject):
    allObjects = c.AllProducts
    path = u'/products/generate'
    
class list_scanners(ListConfigurationObject):
    allObjects = c.AllScanners
    path = u'/scanners/list'
    
class print_scanners(app.page):
    path = u'/scanners/print'

    def GET(self):
        web.header('Content-Type', u'text/html;charset=utf-8')
        return render.scanners_print(c)
    
class get_scanner(GetConfigurationObject):
    allObjects = c.AllScanners
    path = u'/scanner/(.*)'

class save_scanner(SaveConfigurationObject):
    allObjects = c.AllScanners
    path = u'/save/scanner/(.*)/(.*)'
    
class generate_scanner(GenerateConfigurationObject):
    allObjects = c.AllScanners
    path = u'/scanners/generate'
    
class print_config(app.page):
    path = u'/config/print'

    def GET(self):
        web.header('Content-Type', u'text/html;charset=utf-8')
        return render.config_print(c)
    
class index(app.page):
    path = '/'

    def GET(self):
        web.header('Content-Type', u'text/html;charset=utf-8')
        return render.index(c)
        
