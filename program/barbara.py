# -*- coding: utf-8 -*-
#!/usr/bin/env python
# -*- coding: utf-8 -*-

# librairies
#from __future__ import absolute_import, division, print_function, unicode_literals
import evdev
import time
import datetime
import io
import os
import subprocess
import pigpio
import codecs
import sys
import threading
import Tkinter
from Queue import Queue,Empty
import syslog
import socket
import netifaces
import zlib

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

# Code source dans le meme repertoire
import SSD1306
from keypadClass4 import keypad

# For ADC:
from smbus import SMBus
import spidev

#Impression de barcodes = pas nécessaire car généré par l'imprimante...
#import barcode
#from barcode.writer import ImageWriter

from bluetoothScanner import *
from OLEDScreen import *

import barbaraConfig

# Ensure 1234567890128
# UTF-8 for the output terminal
UTF8Writer = codecs.getwriter('utf8')
sys.stdout = UTF8Writer(sys.stdout)
#import locale
#print(sys.stdout.encoding)
#print(sys.stdout.isatty())
#print(locale.getpreferredencoding())
#print(sys.getfilesystemencoding())
#print(os.environ["PYTHONIOENCODING"])

# Hardware configuration (THIS machine!)
import HardConfig
hardConf = HardConfig.HardConfig()

#Application configuration
barbaraConfiguration = barbaraConfig.barbaraConfig(hardConf)
barbaraConfiguration.load()
print barbaraConfiguration.alignPrinter
print "---"
print barbaraConfiguration.printBarcode
print "---"

#Threads may have to stop!
Alive = True

def exec_command(contexte,args):
    outputText = None
    try:
        outputText = subprocess.check_output(args,stderr=subprocess.STDOUT).decode(sys.getdefaultencoding())
    except subprocess.CalledProcessError as anError:
        contexte.message = [u"Statut="+unicode(anError.returncode),unicode(anError)]
        contexte.tk_message()
        print u"Statut="+unicode(anError.returncode)+u" "+unicode(anError)
        return anError.returncode == 0
    except:
        traceback.print_exc()
        return False
    if outputText:
        contexte.message = [outputText]
        contexte.tk_message()
    return True


# Send / Receive UDP broadcast packets
PREFIX_BROADCAST = "BARBARA "

def messageCRC(message):
    return unicode(zlib.crc32(PREFIX_BROADCAST+message))

COMPACT_TIME_FORMAT = u"%y%m%d %H%M%S"
MANUAL_TIME_FORMAT = u"%y%m%d %H%M"

def compactNow():
    return datetime.datetime.now().strftime(COMPACT_TIME_FORMAT)

# Clocks desynchronized ?
def correctClock(remoteTime):
    if remoteTime:
        try:
            remote = datetime.datetime.strptime(remoteTime,COMPACT_TIME_FORMAT)
            if abs(remote - datetime.datetime.now()) > barbaraConfiguration.networkLatency:
                print u"Setting clock to "+unicode(remote)
                outputText = subprocess.check_output([u'sudo',u'date',u'+"'+COMPACT_TIME_FORMAT+u'"','-s',u'"'+remoteTime+u'"'],stderr=subprocess.STDOUT).decode(sys.getdefaultencoding())
        except:
            traceback.print_exc()

#Last battery measure
lastBatt = 0.0

#Data Configuration has to be retrieved localy or remotely...
import Configuration
c = Configuration.c
c.barbaraConfig = barbaraConfiguration

def networkSendBroadcast():

  global Alive
  global stats_label

  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  s.bind(('', 0))
  s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

  while Alive:
    statistics = str(c.AllTransactions.total_buyWithBrace)+"/"+str(c.AllTransactions.total_credit)
    message = barbaraConfiguration.applicationURL+'\t'+statistics+'\t'+compactNow()
    s.sendto(messageCRC(message)+'\t'+message+'\n', ('<broadcast>', barbaraConfiguration.broadcastPort))
    try: # May fail if received too early...
        stats_label.set(statistics)
    except:
        pass
    time.sleep(barbaraConfiguration.broadcastDelay)

scannersLoaded = False

def networkReceiveBroadcast():
  global Alive
  global c
  global scannersLoaded
  global barbaraConfiguration
  global stats_label

  BUFFER_SIZE = 1024
  PORT_NAME = ''

  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  s.bind((PORT_NAME, barbaraConfiguration.broadcastPort))
  s.setblocking(0)

  while Alive:
    result = select.select([s],[],[])
    message = result[0][0].recv(BUFFER_SIZE)

    if message:
        if message[len(message)-1] == '\n': # line correctly ended
            tab = message.find('\t')
            if tab > 0:
                crc = message[:tab]
                netMessage = message[tab+1:len(message)-1]
                try:
                    crc = int(crc)
                    crcMess = int(messageCRC(netMessage))
                except:
                    crc = -1
                    crcMess = -2

                if crc == crcMess:
                    messageParts = netMessage.split('\t')
                    if len(messageParts) >= 3:
                        statistics = messageParts[1]
                        barbaraConfiguration.applicationURL = messageParts[0]
                        correctClock(messageParts[2])
                        if not scannersLoaded:
                            time.sleep(4.0) # Server startup!
                            c.load_remote()
                            scannersLoaded = True
                        print barbaraConfiguration.applicationURL,"=",statistics
                        try: # May fail if received too early...
                            stats_label.set(statistics)
                        except:
                            pass
                    else:
                        print ('UDP message is not in 3 parts:'+message)
                else:                
                    print ('Invalid CRC in UDP:'+message)
            else:                
                print ('No CRC in UDP:'+message)
        else:                
            print ('No EOL in UDP:'+message)

            #if c.timestamp < timestamp:
            #    c.load_remote(barbaraConfiguration)

c.load_local()

# Local IP address
localAddr = u""
for ifaceName in netifaces.interfaces():
  addresses = [anInterface['addr'] for anInterface in netifaces.ifaddresses(ifaceName).setdefault(netifaces.AF_INET, [{'addr':'No IP addr'}] )]
  IP = ', '.join(addresses)
  #print '%s: %s' % (ifaceName, str(IP))
  if (ifaceName != 'lo'):
    if (IP != 'No IP addr'):
      localAddr = IP

if barbaraConfiguration.applicationRole == 'c':
    c.load_remote()
    scannersLoaded = True
    barbaraConfiguration.applicationURL = "http://"+unicode(localAddr)+":"+unicode(barbaraConfiguration.applicationPort)

    threadAPI = threading.Thread(target=c.startWebAPI)
    threadAPI.start()

    threadBROADCAST = threading.Thread(target=networkSendBroadcast)
    threadBROADCAST.daemon = True
    threadBROADCAST.start()

elif barbaraConfiguration.applicationRole == 'b':
    threadBROADCAST = threading.Thread(target=networkReceiveBroadcast)
    threadBROADCAST.daemon = True
    threadBROADCAST.start()
else: # Local Data
    c.load_remote()
    scannersLoaded = True

# Ensure a User BARBARA

CB_User_BARBARA =  "1000000010121"

#if not CB_User_BARBARA in c.AllUsers.elements:
aRow = c.AllUsers.defaultRow(CB_User_BARBARA)
aRow['access'] = u"g"
aRow['name'] = u"BARBARA"
c.AllUsers.assignObject(CB_User_BARBARA,aRow)

# Ensure a USB Scanner

MAC_USB_Scanner =  "AFANDBARCODE"

if not MAC_USB_Scanner in c.AllScanners.elements:
    aRow = c.AllScanners.defaultRow(MAC_USB_Scanner)
    aRow[u'client'] = c.barbaraConfig.akuinoHost
    c.AllScanners.assignObject(MAC_USB_Scanner,aRow)

PIG = pigpio.pi()
if hardConf.running:
    PIG.set_mode(hardConf.running, pigpio.OUTPUT)
    PIG.write(hardConf.running, 0)


if hardConf.oled:
# 128x64 display with hardware I2C:
    screen = OLEDScreen(True, disp = SSD1306.SSD1305_132_64(rst=hardConf.oled_reset,gpio=PIG))
else:
    screen = OLEDScreen(False, disp = None)


TAILLE_ECRAN = 4 # nombre d'elements que l'on affiche à la fois dans les stocks et la facture

baseDirIMG = "static/img/"

bluetooth = bluetoothScanner();
bluetooth.config = c
bluetooth.screen = screen

lock = threading.RLock()

badgingdev =""

scancodes = {
    # Scancode: ASCIICode
    0: None, 1: u'ESC', 2: u'1', 3: u'2', 4: u'3', 5: u'4', 6: u'5', 7: u'6', 8: u'7', 9: u'8',
    10: u'9', 11: u'0', 12: u'-', 13: u'=', 14: u'BKSP', 15: u'TAB', 16: u'q', 17: u'w', 18: u'e', 19: u'r',
    20: u't', 21: u'y', 22: u'u', 23: u'i', 24: u'o', 25: u'p', 26: u'[', 27: u']', 28: u'CRLF', 29: u'LCTRL',
    30: u'a', 31: u's', 32: u'd', 33: u'f', 34: u'g', 35: u'h', 36: u'j', 37: u'k', 38: u'l', 39: u';',
    40: u'"', 41: u'`', 42: u'LSHFT', 43: u'\\', 44: u'z', 45: u'x', 46: u'c', 47: u'v', 48: u'b', 49: u'n',
    50: u'm', 51: u',', 52: u'.', 53: u'/', 54: u'RSHFT', 56: u'LALT', 100: u'RALT'
}

capscodes = {
    0: None, 1: u'ESC', 2: u'!', 3: u'@', 4: u'#', 5: u'$', 6: u'%', 7: u'^', 8: u'&', 9: u'*',
    10: u'(', 11: u')', 12: u'_', 13: u'+', 14: u'BKSP', 15: u'TAB', 16: u'Q', 17: u'W', 18: u'E', 19: u'R',
    20: u'T', 21: u'Y', 22: u'U', 23: u'I', 24: u'O', 25: u'P', 26: u'{', 27: u'}', 28: u'CRLF', 29: u'LCTRL',
    30: u'A', 31: u'S', 32: u'D', 33: u'F', 34: u'G', 35: u'H', 36: u'J', 37: u'K', 38: u'L', 39: u':',
    40: u'\'', 41: u'~', 42: u'LSHFT', 43: u'|', 44: u'Z', 45: u'X', 46: u'C', 47: u'V', 48: u'B', 49: u'N',
    50: u'M', 51: u'<', 52: u'>', 53: u'?', 54: u'RSHFT', 56: u'LALT', 100: u'RALT'
}

accented = [u'é',u'è',u'ç',u'à',u'ù',u'ä',u'ë',u'ï',u'ö',u'ü',u'â',u'ê',u'î',u'ô',u'û']

def setMessages(modes):
    for aMode in modes:
        if aMode in c.AllMessages.elements:
            label = c.AllMessages.elements[aMode].fields[barbaraConfiguration.language]
            if label:
                modes[aMode] = label
    
# MODES 
CB_User_Cancel =  "1000000010077"
CB_Vente_Bracelets = "1000000010039"
CB_Vente_Produits = "1000000010053"
CB_Stock = "1000000010114"
CB_Collabs = "1000000011036"
CB_Scanners = "1000000011043"
CB_Gestion = "1000000011050"

modes = {
         CB_User_Cancel: "Log In",
         CB_Vente_Bracelets: "Bracelet",
         CB_Vente_Produits : "Produits",
         CB_Stock : "Stock",
         CB_Collabs : "Collabs",
         CB_Gestion : "Config",
         CB_Scanners: "BlueTth"
         }
setMessages(modes)

    # ACTIONS UTILISABLES DANS CERTAINS MODES 
CB_Suivant = "1000000010084"       # Utilisé dans la consultation de la facture, des stocks, des collaborateurs
CB_Precedent = "1000000010091"     # Idem
CB_Cash = "1000000010015"          # Paiement par Cash + Activer/Sauver les données de l'utilisateur (nom+droits), du produit (nom+prix), du scanner
CB_Carte = "1000000010022"         # Paiement par Carte + Désactiver(Sauver les données de) l'utilisateur (nom+droits), du produit (nom+prix), du scanner
CB_Arbitraire = "1000000010107"    # Code barre suivant est pris de manière arbitraire...
CB_Modifier = "1000000010046"      # Enlever au lieu d'ajouter des produits au panier
CB_Generer =  "1000000011005"      # Impression d'un code barre arbitraire
CB_Initialiser =  "1000000011012"  # Initialiser l'imprimante, lancer un scan Bluetooth
CB_Effacer_Nombre =  "1000000011098" # Mettre le nombre complètement à zéro
#TODO:
#CB_Nouveau = Accepter un code-barre "extérieur" qui n'existe pas ailleurs dans le systeme
#CB_Regenerer = Reimprimer le dernier code barre accede
#CB_ChoixA,B,C,... Choisir un des items affichés (liste suivant/precedent)
CB_Shutdown = "1000000011067"

actions = {CB_Suivant : "Suivant",
           CB_Precedent : "Precedent",
           CB_Cash:"Cash",
           CB_Carte:"Carte",
           CB_Arbitraire:  "Nouveau",
           CB_Modifier: "Modifier",
           CB_Generer: "Generer",
           CB_Initialiser: "Initialiser",
           CB_Effacer_Nombre: "Zéro",
           CB_Shutdown : "TOUT FERMER"
           }
setMessages(actions)

menu_choices = {"1000000012019":1,
                "1000000012026":2,
                "1000000012033":3,
                "1000000012040":4,
                "1000000012057":5,
                "1000000012064":6,
                "1000000012071":7,
                "1000000012088":8,
                "1000000012095":9 }

#BACKGROUND:
color_window = "gray25"
color_canevas = "navy"

#FOREGROUND
color_product = "cyan"
color_client = "magenta"
color_message = "orange"
color_header = "white"
color_debit = "yellow"
color_credit = "chartreuse2"
color_index = "green"

# Preparatio de l'ecran integre : affichage du s, de l'utilisateur et de l'heure
def lcd_screen (contexte) :

    if not hardConf.oled:
        return 0

    global screen

    clear() #effacage de l'écran

    strnow = datetime.datetime.now().strftime("%H:%M")  #affichage de la date et de l'heure
    screen.draw.text((100,1), strnow, font=screen.font,fill=255)
    
    #on affiche le mode sélectionné
    if contexte.mode == CB_Stock :
        screen.draw.text((4,1), contexte.mode, font=screen.font,fill=255)
    else :
        screen.draw.text((4,1), contexte.mode[6:], font=screen.font,fill=255)
        
    color_screen (45,0,80,9)    #on met une partie en évidence pour afficher l'utilisateur courant
    screen.draw.text((50,1), contexte.user.fields["name"], font=screen.font,fill=0)

    return 10

########################## fonctions d'affichage

#permet d'éffacer tout l'écran et de se positionner au début
def clear():

    global screen
    
    screen.linePos = 0
    if hardConf.oled:
        screen.draw.rectangle((screen.begScreen,0,screen.endScreen,63),fill=0)
    
clear() #efface l'écran au début du programme

# Colorie l'ecran en blanc avec les repères reçus 
def color_screen(x0 = screen.begScreen,y0 = 0, x1 = screen.endScreen , y1 = 63) :
    if hardConf.oled:
        global screen
        screen.draw.rectangle((x0,y0,x1,y1),fill = 255)

##def standby (currScanner):
##    if hardConf.oled:
##        
##            if ((screen.linePos == 0) or (screen.linePos > 40) ) :
##                screen.linePos = clear ()
##                strnow = datetime.datetime.now().strftime("%H:%M")
##                screen.draw.text((100,screen.linePos+1), strnow, font=screen.font,fill=255)
##    ##        print '\n' + str(screen.linePos) + '\n'
##    ##        print (nameDev + ' is grab and ready to use \n')
##            screen.draw.text((4,screen.linePos+1),unicode(i), font=screen.font,fill=255)
##            i+= 1
##            #affiche l'utilisateur qui possède l'appareil
##            contexte = None
##            if i in allContexte:
##                contexte = allContexte[i]
##            if contexte != None:
##                if contexte.user :
##                    #print contexte.user.fields["name"]
##                    color_screen(45,screen.linePos,80,screen.linePos +9)
##                    screen.draw.text((50,screen.linePos+1),unicode(contexte.user.fields["name"]), font=screen.font,fill=0)
##                    screen.linePos += screen.lineHeight
##            else :
##                screen.linePos += screen.lineHeight            
##            screen.show()

# Affiche les dizaines et unites pour la vente de produits et bracelets
def ecran_qty(contexte) :
    if hardConf.oled:
        global screen
        
        screen.linePos += screen.lineHeight
        pos = 15
        screen.draw.text((pos,screen.linePos+1),(" Dizaines :"), font=screen.font,fill=255)
        (x,y) = screen.draw.textsize ((" Dizaines :"),font=screen.font) #on récupère la position ou le texte s'est arrêté
        pos = pos+x
        screen.draw.text((pos,screen.linePos+1),(" || "), font=screen.font,fill=255)
        (x,y) = screen.draw.textsize ((" || "),font=screen.font) #on récupère la position ou le texte s'est arrêté
        pos2 = pos+x
        screen.draw.text((pos2,screen.linePos+1),(" Unites :"), font=screen.font,fill=255)

        screen.linePos += screen.lineHeight
        screen.draw.text((30,screen.linePos+2),unicode(contexte.dizaine/10), font=screen.font16,fill=255)
        screen.draw.text((pos,screen.linePos+1),(" || "), font=screen.font16,fill=255)
        (x,y) = screen.draw.textsize ((" || "),font=screen.font16) #on récupère la position ou le texte s'est arrêté
        screen.draw.text((pos2+15,screen.linePos+2),unicode(contexte.unite), font=screen.font16,fill=255)
        
        if contexte.qty_choisie != -1 :
            screen.linePos += screen.lineHeight
            screen.draw.text((40,screen.linePos+1),"Total Qty : " + unicode(contexte.qty_choisie), font=screen.font16,fill=255)

        screen.show()
    
# Ecran vente des produits : affiche le nom du produit, son prix la quantite choisie et le total pour ce produit ainsi que pour le panier
def ecran_vente_produits(contexte):    

    #print "ECRAN DE VENTE PRODUITS"
    
    if contexte.produit != None :   #si il y a un produit, on l'affiche avec la quantité choisie, son prix et le total (contexte.client après calcul) pour ce produit
        if hardConf.oled:
            global screen
            #preparationd de l'écran
            screen.linePos = lcd_screen(contexte)
         
            screen.linePos += screen.lineHeight
            screen.draw.text((4,screen.linePos+1), contexte.produit.fields["name"], font=screen.font,fill=255)
            screen.linePos += screen.lineHeight
            
            # mise en float du prix récupéré à partir du fichier CSV
            prix = contexte.produit.getCents()/100.0
            #print prix
            #calcul du total
            total = contexte.panier[contexte.produit] * prix
            #affichage
            pos = 4     #position de départ
            
            screen.draw.text((pos,screen.linePos+1),(unicode(contexte.panier[contexte.produit])), font=screen.font20,fill=255)
            (x,y) = screen.draw.textsize (unicode(contexte.panier[contexte.produit]),font=screen.font20) #on récupère la position ou le texte s'est arrêté
            pos = pos+x
            
            screen.draw.text((pos,screen.linePos+11), (" x "), font=screen.font,fill=255)        
            (x,y) = screen.draw.textsize ((" x "),font=screen.font) #on récupère la position ou le texte s'est arrêté
            pos = pos+x
            
            screen.draw.text((pos,screen.linePos+11), (unicode(contexte.produit.fields["price"])), font=screen.font16,fill=255)        
            (x,y) = screen.draw.textsize (unicode(contexte.produit.fields["price"]),font=screen.font16) #on récupère la position ou le texte s'est arrêté
            pos = pos+x
            
            screen.draw.text((pos,screen.linePos+11), (screen.euro + " ") , font=screen.font,fill=255)
            pos = pos + 5  #    ici, on ne fait pas appel à la fonction car "screen.euro" est en unicode 
            #print pos      #        et la fonction de calcul de la position ne l'accepte pas
            
            screen.draw.text((pos,screen.linePos+11), " = " + unicode(total), font=screen.font16,fill=255)
            (x,y) = screen.draw.textsize (" = " + unicode(total), font=screen.font16) #on récupère la position ou le texte s'est arrêté
            pos = pos+x
            
            screen.draw.text((pos,screen.linePos+11), (" " + screen.euro) , font=screen.font,fill=255)

            screen.linePos += screen.lineHeight
            total,bouteilles = contexte.total_panier(contexte.panier)
            #print total
            screen.draw.text((4,screen.linePos+11), ("Total : " + unicode(total)+ " " + screen.euro)  , font=screen.font,fill=255)

            screen.show()
            
        contexte.tk_vente_produits()
    else :
        ecran_qty(contexte)

# Ecran d'affichage des stocks, une fois le mode active, on peut soit consulter tout le stock ou bien seulement un produit à la fois
# Comme la recuperation des produits se fait à partir d'une bibliotheque, l'ordre peut varier
def ecran_stock(contexte,all_stock = False) :
    #print "ECRAN DES STOCKS"

    if not all_stock:
        ecran_produit(contexte)
        return

    contexte.syncListe(c.AllProducts.elements_refreshed())                
    contexte.tk_stock(all_stock)   

    if hardConf.oled:
        global screen
        #Préparation de l'écran
        lcd_screen(contexte)

        for key in c.AllProducts.elements.keys()[contexte.debut : contexte.fin]:
            objet = c.AllProducts.elements[key]
            print objet.fields['barcode'] + " " + objet.fields['name'] + " " + objet.fields['price'] + " " + objet.fields['qty']
                
            screen.linePos += screen.lineHeight
            pos = 4

            screen.draw.text((pos,screen.linePos+1), objet.fields['name'][:15] , font=screen.font16,fill=255)

            screen.draw.text((100,screen.linePos+1), objet.fields['price'] + " " , font=screen.font16,fill=255)
   
            screen.draw.text((120,screen.linePos+1), objet.fields['qty'] , font=screen.font16,fill=255)
     
        screen.show()

# Ecran d'affichage des collaborateurs, une fois le mode active, on peut soit consulter toute la liste ou bien seulement un utilisateur à la fois
# Comme la recuperation des produits se fait à partir d'une bibliotheque, l'ordre peut varier
def ecran_collaborateurs(contexte,all_collabs = False) :
    #print "ECRAN DES COLLABORATEURS"

    if not all_collabs:
        ecran_utilisateur(contexte)
        return

    contexte.syncListe(c.AllUsers.elements_refreshed())                
    contexte.tk_collaborateurs(all_collabs)   

    if hardConf.oled:
        global screen
        #Préparation de l'écran
        lcd_screen(contexte)

        for key in c.AllUsers.elements.keys()[contexte.debut : contexte.fin]:
            objet = c.AllUsers.elements[key]
            print objet.fields['barcode'] + " " + objet.fields['name'] + " " + objet.fields['price'] + " " + objet.fields['qty']
                
            screen.linePos += screen.lineHeight
            pos = 4

            screen.draw.text((pos,screen.linePos+1), objet.fields['name'][:15] , font=screen.font16,fill=255)

            screen.draw.text((100,screen.linePos+1), objet.fields['access'] + " " , font=screen.font16,fill=255)

        screen.show()

# Ecran d'affichage des scanners, une fois le mode active, on peut soit consulter toute la liste ou bien seulement un scanner à la fois
def ecran_scanners(contexte,all_scanners = False) :
    #print "ECRAN DES SCANNERS"

    if not all_scanners:
        ecran_scanner(contexte)
        return

    contexte.syncListe(c.AllScanners.elements_refreshed())                
    contexte.tk_scanners(all_scanners)   

    if hardConf.oled:
        global screen
        #Préparation de l'écran
        lcd_screen(contexte)

        for key in c.AllScanners.elements.keys()[contexte.debut : contexte.fin]:
            objet = c.AllScanners.elements[key]
            print objet.id + " " + objet.fields['name'] + " " + objet.fields['pin'] + " " + objet.fields['deny']
                
            screen.linePos += screen.lineHeight
            pos = 4

            screen.draw.text((pos,screen.linePos+1), objet.id, font=screen.font,fill=255)
            
            screen.draw.text((70,screen.linePos+1), " " + objet.fields["name"][:10] +" " , font=screen.font16,fill=255)
            
            screen.draw.text((80,screen.linePos+1), " " + objet.fields["pin"], font=screen.font9,fill=255)
            
            screen.draw.text((90,screen.linePos+1), objet.strActive(), font=screen.font16,fill=255)

        screen.show()

# Ecran de facture : affiche les elements actuellement présent dans le panier
def ecran_facture(contexte) :
    #print "ECRAN DE FACTURE"
    
    contexte.syncListe(contexte.prev_panier)                
    contexte.tk_facture()

    if hardConf.oled:                
        global screen
        #Préparation de l'écran
        screen.linePos = lcd_screen(contexte)
        print "Votre Facture : "
        index = contexte.debut
        for element in contexte.prev_panier.keys() [contexte.debut : contexte.fin]:            
            #récupération des infos à partir de la base de données

            #print ("The price of one {} is {} euros \nYou took {} of them" .format(element.fields["name"], element.fields["price"], contexte.panier[element])) #affichage d'une "Facture"
                        
            price = element.getCents()/100.0 #on met le prix en float
        
            #calcul du total
            total = (price * float(contexte.prev_panier[element]))
                                               

            screen.linePos += screen.lineHeight
            pos = 4
            screen.draw.text((pos,screen.linePos+1), unicode(index) , font=screen.font16,fill=255)
            (x,y) = screen.draw.textsize (unicode(index),font=screen.font16) #on récupère la position ou le texte s'est arrêté
            pos = pos+x

            screen.draw.text((pos,screen.linePos+1), " " + element.fields["name"][:10] +". " , font=screen.font16,fill=255)
            
            screen.draw.text((70,screen.linePos+1), " " + unicode(contexte.prev_panier[element]) + " " , font=screen.font16,fill=255)
            
            screen.draw.text((80,screen.linePos+1), " " + unicode(element.fields["price"]) + " " , font=screen.font16,fill=255)
            
            screen.draw.text((90,screen.linePos+1), " " +unicode(total) , font=screen.font16,fill=255)
            index+=1

        screen.show()
        
# Lors de la vente de produits, une fois le client scanne, on affiche son solde, le montant à payer ainsi que ce  qui lui reste sur son bracelet
def ecran_transaction_client(contexte):  #lors de la vente de produit !
    #print "ECRAN DE TRANSACTION"
    contexte.tk_transaction_client()    

    if hardConf.oled:
        global screen
        #Préparation de l'écran
        screen.linePos = lcd_screen(contexte)
        
        solde = contexte.client.fields["amount"] #acquisition du solde du bracelet
        solde = Configuration.infloat(solde)
        total,bouteilles = contexte.total_panier(contexte.panier)
        reste = solde - total
        reste = unicode(reste)

        screen.linePos += screen.lineHeight
        pos = 4
        screen.draw.text((pos,screen.linePos+1), unicode(solde) , font=screen.font16,fill=255)
        (x,y) = screen.draw.textsize ((unicode(solde)),font=screen.font16) #on récupère la position ou le texte s'est arrêté
        pos = pos+x
        
        screen.draw.text((pos,screen.linePos+7), (screen.euro) , font=screen.font,fill=255)
        pos = pos + 5  #    ici, on ne fait pas appel à la fonction car "screen.euro" est en unicode 
        #print pos      #        et la fonction de calcul de la position ne l'accepte pas
        
        screen.draw.text((pos,screen.linePos+1), " - " + unicode(total) , font=screen.font16,fill=255)
        (x,y) = screen.draw.textsize ((" - " + unicode(total)),font=screen.font16) #on récupère la position ou le texte s'est arrêté
        pos = pos+x
        screen.draw.text((pos,screen.linePos+7), (screen.euro) , font=screen.font,fill=255)

        screen.linePos += 2*screen.lineHeight
            
        pos = 4
        screen.draw.text((pos,screen.linePos+11),(" = "), font=screen.font,fill=255)
        (x,y) = screen.draw.textsize ((" = "),font=screen.font) #on récupère la position ou le texte s'est arrêté
        pos = pos+x
        screen.draw.text((pos,screen.linePos+1),(reste), font=screen.font20,fill=255)
        (x,y) = screen.draw.textsize ((reste),font=screen.font20) #on récupère la position ou le texte s'est arrêté
        pos = pos+x
        screen.draw.text((pos,screen.linePos+11), (screen.euro) , font=screen.font,fill=255)

    screen.show()


# Affichage de l'ecran ou on demande le moyen de paiement, on lui montre son solde apres le chargement/achat du bracelet
def ecran_vente_bracelets(contexte, charge):
    #print "ECRAN DE VENTE DES BRACELETS"
    
    if contexte.client != None :
        contexte.tk_vente_bracelets(charge)
        if hardConf.oled:
            global screen
            #Préparation de l'écran
            screen.linePos = lcd_screen(contexte)
    ##        screen.linePos += screen.lineHeight
    ##        screen.draw.text((4,screen.linePos+1), contexte.client.fields["barcode"], font=screen.font,fill=255)
            if contexte.qty_choisie < 0 :
                montant = barbaraConfiguration.defaultAmount
            else:
                montant = contexte.qty_choisie

            screen.linePos += screen.lineHeight
            screen.draw.text((4,screen.linePos+1), "Montant recharge : " + unicode(montant) + screen.euro , font=screen.font16,fill=255)
                
            if charge :
                screen.linePos += screen.lineHeight*1.5
                screen.draw.text((4,screen.linePos+1), "Cash ou Carte ?" , font=screen.font,fill=255)
                screen.linePos += screen.lineHeight
                screen.draw.text((4,screen.linePos+1), "Annuler ?" , font=screen.font,fill=255)
            else:
                screen.linePos += screen.lineHeight
                screen.draw.text((4,screen.linePos+1), "Chargement effectue" , font=screen.font,fill=255)
                screen.linePos += screen.lineHeight
                screen.draw.text((4,screen.linePos+1), "Montant actuel : " + contexte.client.fields["amount"], font=screen.font,fill=255)
                screen.linePos += screen.lineHeight
                screen.draw.text((4,screen.linePos+1), "Bonne soiree !" , font=screen.font,fill=255)
                
            screen.show()

    else :
        ecran_qty(contexte)

# TRUE if no problem to create Print job
def linePrinter(contexte,barcode,someText):
    print "Printing using "+barbaraConfiguration.printDirectory+barcode+".txt"
    with open (barbaraConfiguration.printDirectory+barcode+".txt","w") as printFile:
        printFile.write(someText)
    return exec_command(contexte,["lpr","-o","raw","-r",barbaraConfiguration.printDirectory+barcode+".txt"])

def linePrinterObject(contexte,objectToPrint,printerString):
    return linePrinter(contexte,objectToPrint.id,printerString % { "barcode":objectToPrint.id, "name":objectToPrint.name(c) } )

# Affichage de l'ecran et surtout impression d'un bracelet
def generer_bracelet(contexte):
    #print "ECRAN D'IMPRESSION D'UN BRACELET"
    global c
    
    printedBrace = None
    printerString = barbaraConfiguration.printBarcode
    if printerString:
        aBrace = c.AllBraces.generateBarcode()
        if aBrace:
            if linePrinterObject(contexte,aBrace,printerString):
                printedBrace = aBrace
                contexte.client = printedBrace
                printedBrace.fields["sold"] = "printing"
    ##REM DIRECTION 0
    ##REM BLINE 3 mm,-20 mm
    ##REM SIZE 24 mm,80 mm
    ##REM BLINEDETECT
    ##CLS
    ##OUT "PAPER Size=";GETSETTING$(CB_Gestion,"TSPL","PAPER SIZE")
    ##TEXT 180,10,"2",90,1,1,"BARBARA"
    ##BARCODE 145,10,"EAN13",100,1,90,4,4,"923456789010"
    ##REM DISPLAY IMAGE
    ##PRINT 1
    ##REM DISPLAY OFF
    ##            aWriter=ImageWriter()
    ##            aWriter.set_options({"dpi":203,"text_distance":2})
    ##            ean = barcode.get("ean13",codeBarre,aWriter)
    ##            filename = ean.save("/var/akuino/"+codeBarre)
    ##            print(os.system("lpr -o media=Custom.28x292mm -o fit-to-page -o position=bottom "+filename)) # -r to keep /var tidy !
    #            if linePrinter(contexte,codeBarre,"DIRECTION 0\r\nBLINE 3 mm,-18 mm\r\nSIZE 24 mm,80 mm\r\nCLS\r\nTEXT 180,20,\"2\",90,1,1,\"BARBARA\"\r\nBARCODE 145,20,\"EAN13\",100,1,90,4,4,\""+codeBarre+"\"\r\nPRINT 1\r\n"):
            else:
                ecran_message(contexte,0,u"Imprimante",u"pas disponible?")
        else:
            ecran_message(contexte,0,u"Plus de bracelets définis",u"pour l'impression.")
    else:
        ecran_message(contexte,0,u"Imprimante",u"pas configuree?")
    if printedBrace:
        ecran_client(contexte)
    else:
        ecran_message(contexte,0,u"!Contactez votre installateur.")

# Affichage de l'ecran et surtout impression d'un bracelet
def generer_produit(contexte):
    #print "ECRAN D'IMPRESSION D'UN BRACELET"
    global c
    
    printedBrace = None
    printerString = barbaraConfiguration.printBarcode
    if printerString:
        aBrace = c.AllProducts.generateBarcode()
        if aBrace:
            if linePrinterObject(contexte,aBrace,printerString):
                printedBrace = aBrace
                contexte.produit = printedBrace

    if printedBrace:
        ecran_produit(contexte)
    else:
        ecran_message(contexte,0,u"Plus de bracelets définis",u"pour l'impression.",u"!Contactez votre installateur.")

# Affichage de l'ecran et surtout impression d'un bracelet
def generer_utilisateur(contexte):
    #print "ECRAN D'IMPRESSION D'UN BRACELET"
    global c
    
    printedBrace = None
    printerString = barbaraConfiguration.printBarcode
    if printerString:
        aBrace = c.AllUsers.generateBarcode()
        if aBrace:
            if linePrinterObject(contexte,aBrace,printerString):
                printedBrace = aBrace
                contexte.utilisateur = printedBrace

    if printedBrace:
        contexte.nom_choisi = contexte.utilisateur.fields["name"]
        contexte.setQty(contexte.utilisateur.getAccessCode())
        ecran_utilisateur(contexte)
    else:
        ecran_message(contexte,0,u"Plus de bracelets définis",u"pour l'impression.",u"!Contactez votre installateur.")

# Affichage de l'ecran et surtout impression d'un bracelet
def ecran_sync_printer(contexte):
    #print "ECRAN DE SYNCHRO DE L'IMPRIMANTE"
    global c
    printerString = barbaraConfiguration.alignPrinter
    if printerString:
        print "Printer Align..."
    #    linePrinter(contexte,"align","DIRECTION 0\r\nBLINE 3 mm,-20 mm\r\nSIZE 24 mm,80 mm\r\nBLINEDETECT\r\n")
        linePrinter(contexte,"align",printerString)
        ecran_message(contexte,0,u"Resynchronisation",u"de la position du ruban",u"de bracelets.")
    
# Cette fonction permet de récupérer des messages et ensuite de les afficher
def ecran_message(contexte,reset = 0, *messages):

    if reset == 0 :
        contexte.message = []
    for msg in messages :
        if msg in contexte.message :
            pass
        else :
            contexte.message.append(msg)
        print msg

    if reset == 2 :
        return

    contexte.tk_message()

    if hardConf.oled:
        global screen
        clear() #effacage de l'écran
        for msg in contexte.message :
            screen.draw.text((4,screen.linePos+1), unicode(msg), font=screen.font,fill=255)
            screen.linePos += screen.lineHeight
            
            if (contexte.message.index(msg) +1) % 5 == 0 :
                
                screen.show()
                
                time.sleep(0.02)
                clear() #effacage de l'ecran
                screen.linePos = 0

# Affichage du code barre Utilisateur et de ses caractéristiques
def ecran_utilisateur(contexte):
    
    contexte.tk_utilisateur()
    if hardConf.oled:
        global screen
        clear()
        strnow = datetime.datetime.now().strftime("%H:%M")
        screen.draw.text((100,screen.linePos+1), strnow, font=screen.font,fill=255)
        screen.linePos = screen.lineHeight * 2
        screen.draw.text((30,screen.linePos+1), contexte.client.fields["barcode"], font=screen.font,fill=255)
        screen.linePos += screen.lineHeight
        pos = 50
        screen.draw.text((pos,screen.linePos+1), contexte.client.fields["name"], font=screen.font,fill=255)
        screen.linePos += screen.lineHeight
        pos = 50
        screen.draw.text((pos,screen.linePos+1), contexte.client.getAccessCode(), font=screen.font,fill=255)
            
        screen.show()


# Affichage du code barre client et de son solde
def ecran_client(contexte):
    
    contexte.tk_client()
    if hardConf.oled:
        global screen
        clear()
        strnow = datetime.datetime.now().strftime("%H:%M")
        screen.draw.text((100,screen.linePos+1), strnow, font=screen.font,fill=255)
        screen.linePos = screen.lineHeight * 2
        screen.draw.text((30,screen.linePos+1), contexte.client.fields["barcode"], font=screen.font,fill=255)
        screen.linePos += screen.lineHeight
        pos = 50
        screen.draw.text((pos,screen.linePos+1), contexte.client.fields["amount"], font=screen.font16,fill=255)
        (x,y) = screen.draw.textsize (contexte.client.fields["amount"],font=screen.font16) #on récupère la position ou le texte s'est arrêté
        pos = pos+x
        screen.draw.text((pos,screen.linePos+7), screen.euro, font=screen.font,fill=255)
            
        screen.show()

# Affichage du nom du produit, de son code barre et de son prix
def ecran_produit(contexte):
    
    contexte.tk_produit()
    if hardConf.oled:
        global screen
        clear()
        strnow = datetime.datetime.now().strftime("%H:%M")
        screen.draw.text((100,screen.linePos+1), strnow, font=screen.font,fill=255)
        screen.linePos = screen.lineHeight 
        screen.draw.text((15,screen.linePos+1), contexte.produit.fields["name"], font=screen.font,fill=255)
        screen.linePos += screen.lineHeight
        screen.draw.text((30,screen.linePos+1), contexte.produit.fields['barcode'], font=screen.font,fill=255)
        screen.linePos += screen.lineHeight
        pos = 50
        screen.draw.text((pos,screen.linePos+1), contexte.produit.fields["price"], font=screen.font16,fill=255)
        (x,y) = screen.draw.textsize ((contexte.produit.fields["price"]),font=screen.font16) #on récupère la position ou le texte s'est arrêté
        pos = pos+x
        screen.draw.text((pos,screen.linePos+7), screen.euro, font=screen.font,fill=255)
        
        screen.show()

# Affichage du nom du produit, de son code barre et de son prix
def ecran_scanner(contexte):
    
    contexte.tk_scanner()
    if hardConf.oled:
        global screen
        clear()
        strnow = datetime.datetime.now().strftime("%H:%M")
        screen.draw.text((100,screen.linePos+1), strnow, font=screen.font,fill=255)
        screen.linePos = screen.lineHeight 
        screen.draw.text((15,screen.linePos+1), contexte.scanner.idd, font=screen.font,fill=255)
        screen.linePos += screen.lineHeight
        screen.draw.text((30,screen.linePos+1), contexte.scanner.fields['name'], font=screen.font16,fill=255)
        screen.linePos += screen.lineHeight
        screen.draw.text((50,screen.linePos+1), contexte.scanner.fields["pin"], font=screen.font,fill=255)
        screen.linePos += screen.lineHeight
        screen.draw.text((50,screen.linePos+1), contexte.scanner.strActive(), font=screen.font16,fill=255)
        screen.show()

# Affichage du numero de l'apparreil, de son nom et du code barre
##def displayData(res,name,numDev):
##    screen.linePos = clear() #effacage de l'écran
##    strnow = datetime.datetime.now().strftime("%H:%M")
##    screen.draw.text((100,screen.linePos+1), strnow, font=screen.font,fill=255)
##    screen.draw.text((3,screen.linePos+1), str(numDev), font=screen.font,fill=255)
##    screen.draw.text((13,screen.linePos+1), name, font=screen.font,fill=255)
##    screen.linePos += screen.lineHeight
##    screen.draw.text((4,screen.linePos+1), res, font=screen.font,fill=255)
##
##    screen.show()


def aFont(size):
   return ("",size,"bold")

# acquisition des parametres de l'écran au démarage du programme (résolution)
tkdisplay_root = Tkinter.Tk()
#tkdisplay_root.after(50,tkdisplay_root.quit)
screen_height = tkdisplay_root.winfo_screenheight() - 48
net_screen_height = screen_height - 32 - 4 - 8
screen_width = tkdisplay_root.winfo_screenwidth()

while not scannersLoaded:
    print "Waiting for Central server"
    time.sleep(2)

MAX_TILES = c.AllScanners.countActive()
if MAX_TILES < 1:
    MAX_TILES = 1
elif MAX_TILES > 6:
    MAX_TILES = 6

if MAX_TILES == 1:
    tile_height = net_screen_height
    tile_width = screen_width
elif MAX_TILES == 2:
    tile_height = net_screen_height
    tile_width = int(screen_width / 2)
elif MAX_TILES <= 4:
    tile_height = int(net_screen_height / 2)
    tile_width = int(screen_width / 2)
else:
    tile_height = int(net_screen_height / 2)
    tile_width = int(screen_width / 3)

tkdisplay_root.geometry(unicode(screen_width)+"x"+unicode(screen_height))
tkdisplay_root.minsize(width=screen_width,height=screen_height)
tkdisplay_root.resizable(width=False,height=False)
frame_height = tile_height - 20
frame_width = tile_width - 4 - 8
print "Screen : "+ unicode(screen_width) + "x" + unicode(screen_height)

logo = Tkinter.PhotoImage(file = baseDirIMG+"AKUINO.gif")
logo_frame = Tkinter.Canvas(tkdisplay_root, background = 'black', height = logo.height(), width = logo.width())
draw_logo = logo_frame.create_image(1,1,image = logo,anchor=Tkinter.NW,state=Tkinter.NORMAL)
logo_frame.place(anchor=Tkinter.CENTER,x=screen_width/2, y=screen_height/2)  

stats_label = Tkinter.StringVar(tkdisplay_root)

stat_frame = Tkinter.Canvas(tkdisplay_root, background = 'black', height = 32, width = screen_width)
stat_frame.place(anchor=Tkinter.CENTER,x=screen_width/2, y=screen_height-32)  
stat_time = Tkinter.Label(stat_frame, textvariable = stats_label,background = color_canevas, foreground = color_header, font = aFont(18)) 
stat_time.place(anchor=Tkinter.NW, x = 1 , y = 1) #positionnement

allContexte = { }
# Classe contexte, c'est ici que l'on gère le code barre scanné
class Contexte (): #threading.Thread

    startRes = None
    pref_qty = u"€ "
    pref_nom = u"Nom:"
        

    def partial_init(self):
        self.client = None
        self.produit = None
        self.utilisateur = None # Utilisateur en cours de modification
        self.scanner = None # Scanner sur lequel on fait une modification (accepter/rejeter)
        self.panier = {}
        self.arbitraire = False

        self.setQty(-1)
        self.nom_choisi = u""
        self.modifier = False
        self.debut = 0

        self.charge = False
        self.wait = datetime.datetime.now()

    def reinit(self,anUser, save_mode = None):
        self.user = anUser # Utilisateur loggé
        self.mode = save_mode
        self.partial_init()
        self.tkdisplay_started = False
        
        self.message = []

    def __init__(self,rank,scanid):
        #threading.Thread.__init__(self)
        self.canevas = None
        self.t_qty_nbre = None
        self.reinit(None,None)
        self.inputQueue = Queue()
        self.rank = rank
        self.currScanner = None
        if scanid:
            self.currScanner = c.AllScanners.elements[scanid] # Scanner que l'on a en main!
        self.prev_panier = {}

        global screen_height, screen_width

        self.pref_qty = u"€ "
        self.pref_nom = u"Nom:"
        
        self.logo = None
        self.image = None
        self.draw = None
        
        p_x = tile_width * (self.rank % 3)
        p_y = tile_height * int(self.rank / 3)

        self.window = Tkinter.LabelFrame (tkdisplay_root, text = unicode(self.rank)+'#'+(unicode(self.currScanner.id)+'#'+unicode(self.currScanner.fields["name"])) if self.currScanner else u"", borderwidth = 2, labelanchor = 'n', bg = color_window,fg = "white")
        self.window.place(height = tile_height, width = tile_width, x=p_x, y=p_y )
        self.l_frame = self.window

    def setQty(self,val):
        if val <= 0:
            self.qty_choisie = -1
            self.z5 = 0
            self.z4 = 0
            self.z3 = 0
            self.z2 = 0
            self.z1 = 0
            self.unite = 0
        else:
            val = str(val)
            if len(val) >= 1:
                self.unite = int(val[-1])
                if len(val) >= 2:
                    self.z1 = int(val[-2])
                    if len(val) >= 3:
                        self.z2 = int(val[-3])
                        if len(val) >= 4:
                            self.z3 = int(val[-4])
                            if len(val) >= 5:
                                self.z4 = int(val[-5])
                                if len(val) >= 6:
                                    self.z5 = int(val[-6])
        
    def syncListe(self,elements):
        nbElem = len(elements)
        if self.debut >= nbElem :
            self.debut = 0
        elif self.debut < 0 :
            self.debut = 0
        self.fin  = self.debut +  TAILLE_ECRAN
        if self.fin > nbElem :
            self.fin = nbElem
        return nbElem

    def syncChoix(self,index,elements):
        self.syncListe(elements)
        index = index + self.debut
        if index >= self.fin:
            return None
        key = elements.keys()[index]
        return elements[key]

    # Fonction TKINTER : affiche le numero de l'utilisateur en bas à droite
    def number(self) :
        #Emplacement CONSTANT
        self.pos_Y = frame_height-45
        self.pos_X = 10

        if self.t_qty_nbre:
            self.canevas.delete(self.t_qty_nbre)
        else:
            # was self.rank
            t_number = Tkinter.Label(self.canevas, text = self.currScanner.fields["name"] ,background = "yellow", foreground = 'black', font = aFont(26))
            t_number.place(anchor=Tkinter.SE, x = frame_width, y = frame_height) #positionnement
            
        self.t_qty_nbre = self.canevas.create_text(self.pos_X, self.pos_Y-4, anchor = 'nw', fill = color_debit, font = aFont(26))
        if self.qty_choisie != -1:
            self.canevas.itemconfig(self.t_qty_nbre,text=self.pref_qty+unicode(self.qty_choisie)+u"  "+self.pref_nom+self.nom_choisi)
        else:
            self.canevas.itemconfig(self.t_qty_nbre,text=self.pref_nom+self.nom_choisi )


    # Fonction TKINTER : permet d'inserer un interligne d'une taille régulable 
    def saut_de_ligne(self, taille = 80) :

        self.pos_Y += taille   #determination en Y de la position du texte : ici, on rajoute un interligne
        self.pos_X = 1 #on se remet au début de la ligne                      

    # Fonction TKINTER : affiche le symbole screen.euro avec la taile et positionnement demandés
    def euro(self, last_text,taille = 16, anchor_choose  = 'sw', color=color_debit) :
        # symbole screen.euro
        width,height,X,Y = self.size(last_text) #calcul de la largeur en pixel du texte : var, type_var

        Y_position = self.pos_Y
        if anchor_choose  == "sw" :
            Y_position = Y+height
            self.pos_X += width
        elif anchor_choose == 'nw' :
            Y_position = Y
        else :
            self.pos_X += X
        self.t_euro = self.canevas.create_text(self.pos_X, Y_position, anchor = anchor_choose, text = screen.euro , fill = color, font = aFont(taille))

    # Fonction TKINTER : calcul de la taille du texte/label reçu
    def size(self, text_cell):

        #"LABEL" : return text_cell.winfo_reqwidth(),text_cell.winfo_reqheight()

        values =  self.canevas.bbox(text_cell)
        return values[2]-values[0],values[3]-values[1],values[0],values[1]

    # Fonction TKINTER : construction de la partie commune de chaque écran
    def build_tkdisplay(self):

        self.pos_X = self.pos_Y = 1

        if self.canevas != None :
            self.canevas.destroy()
            self.t_qty_nbre = None
        self.canevas = Tkinter.Canvas(self.l_frame, width = frame_width, height = frame_height, bg=color_canevas)
        self.canevas.place(x = 4, y = 0)
        
        #Fond d'écran pour chaque utilisateur : Logo
##        self.logo = Tkinter.Canvas(self.canevas, background = 'black', height = frame_height, width = t_x)
##        self.image = Tkinter.PhotoImage(file = "AKUINO_logo.gif", master = self.window)
##        self.draw = self.logo.create_image(t_x/2,frame_height/2, image = self.image)
##        self.logo.place(height = frame_height, width = t_x)    
##        self.image = Tkinter.PhotoImage(file = "AKUINO_logo.gif", master = self.window)
##        self.logo = self.canevas.create_image(t_x/2,frame_height/2, image = self.image)

               
        #Heure
        strnow = unicode(datetime.datetime.now().strftime("%H:%M"))
        t_time = Tkinter.Label(self.canevas, text = strnow ,background = color_canevas, foreground = color_header, font = aFont(18)) 
        t_time.place(anchor=Tkinter.NE, x = frame_width , y = 1) #positionnement
        
        #Banière commune
        if self.user != None :
            t_user = Tkinter.Label(self.canevas, text = self.user.fields["name"] ,background = "white", foreground = 'black', font = aFont(18))
            if self.mode != None :
                t_mode = Tkinter.Label(self.canevas, text = modes[self.mode],background = color_canevas, foreground = color_header, font = aFont(18))
                
            else :
                t_mode = Tkinter.Label(self.canevas, text = "Choisir Mode",background = color_canevas, foreground = color_header, font = aFont(18))
        else :
            t_user = Tkinter.Label(self.canevas, text = " Identifiez vous ", background = "white", foreground = 'black' , font = aFont(18))
            t_mode = Tkinter.Label(self.canevas, text = " ",background = color_canevas, foreground = color_header, font = aFont(18))
        t_user.place(anchor=Tkinter.N, x = frame_width/2, y = 1) #positionnement
        
        t_mode.place(x = 1, y = 1) #positionnement: pas de calcul ici, car on part du début : (1,1)

        #saut de ligne
        self.saut_de_ligne(120)        # laisser de la place pour "Dizaines" et "Unités"

    def ensure_tkdisplay (self):
        if not self.tkdisplay_started:
            self.tkdisplay_started = True
            self.build_tkdisplay()
            
    # Fonction TKINTER : ici, on reproduit les différents affichages de l'ecran integre sur Tkinter
    def tk_message(self) :
            self.ensure_tkdisplay()
            for msg in self.message :
                self.pos_X = (frame_width-4)/2
                color_fg = color_header
                if msg:
                    if msg[0] == '*':
                        color_fg = color_debit
                        msg = msg[1:]
                    elif msg[0] == '!':
                        color_fg = color_message
                        msg = msg[1:]
                t_msg = self.canevas.create_text(self.pos_X,self.pos_Y,text = msg , fill = color_fg, font = aFont(20))

                self.saut_de_ligne(30)
                #print self.pos_Y
                #print frame_height        

    def close_tkdisplay(self):
            #if self.tkdisplay_started:
            self.number()                 
            self.pos_X = self.pos_Y = 1
            self.sizeX = self.sizeY = None
            self.tkdisplay_started = False
            print ('- - - - -')

    def tk_vente_produits(self) :
            if self.produit == None :
                return

            self.ensure_tkdisplay()
            #Recuperation des valeurs utiles
            # mise en float du prix récupéré à partir du fichier CSV
            prix = self.produit.getCents()/100.0
            #calcul du total
            total = self.panier[self.produit] * prix

            # nom du produit
            self.pos_X = (frame_width-4)/2 #determination en X de la position du Label : ici on centre
            self.pos_Y = frame_height * 0.3
            t_produit = self.canevas.create_text(self.pos_X, self.pos_Y, text = self.produit.fields["name"] , fill= color_header, font = aFont(24))
           
            #saut de ligne
            self.saut_de_ligne(60)   
            
            # quantite
            self.pos_X = (frame_width * 0.3)#determination en X de la position du Label : 1/4 
            t_qty = self.canevas.create_text(self.pos_X, self.pos_Y, anchor = 'nw', text = unicode(self.panier[self.produit]) ,fill = color_message, font = aFont(30))
            
            # foisrs
            width,height,X,Y = self.size (t_qty) #calcul des dimensions en pixel du texte/label : var, type_var
            self.pos_X += width  #determination en X de la position du Label : 1/4 + t_qty
            t_symbole = self.canevas.create_text(self.pos_X, self.pos_Y+12, anchor = 'nw', text = " x " ,fill  = color_header, font = aFont(18))

            # prix du produit
            width,height,X,Y = self.size(t_symbole) #calcul des dimensions en pixel du texte/label : var, type_var
            self.pos_X += width  #determination en X de la position du Label : 2/5 + t_qty + t_symbole
            
            t_price = self.canevas.create_text(self.pos_X, self.pos_Y+8, anchor = 'nw', text = self.produit.fields["price"] , fill = color_message, font = aFont(24))
            save_pos_Y = self.pos_Y
            # symbole screen.euro
            self.euro(t_price,color=color_message)
            self.pos_Y = save_pos_Y
            # egal
            width,height,X,Y = self.size (self.t_euro) #calcul des dimensions en pixel du texte/label : var, type_var
            self.pos_X += width #determination en X de la position du Label : 2/5 + t_qty + t_symbole + t_price + t_euro

            t_symbole = self.canevas.create_text(self.pos_X, self.pos_Y+12, anchor = 'nw', text = " = " , fill = color_header, font = aFont(18))

            # total pour ce produit
            width,height,X,Y = self.size (t_symbole) #calcul des dimensions en pixel du texte/label : var, type_var
            self.pos_X +=  width #determination en X de la position du Label : 2/5 + t_qty + t_symbole + t_price + t_euro + t_symbole
            
            t_total = self.canevas.create_text (self.pos_X, self.pos_Y, anchor = 'nw', text = unicode(total) ,fill = color_debit, font = aFont(30))
            
            # symbole screen.euro
            self.euro(t_total)

            #saut de ligne
            self.saut_de_ligne()   
            
            # total du panier
            total,bouteilles = self.total_panier(self.panier)
            self.pos_X = frame_width * 0.5 #determination en X de la position du Label : ici on centre
            t_total = self.canevas.create_text(self.pos_X,self.pos_Y,anchor = 'n',text =  unicode(bouteilles)+u" produit"+("s" if bouteilles > 1 else u""), fill = color_message, font = aFont(20))
            self.saut_de_ligne(45)   
            self.pos_X = frame_width * 0.5 #determination en X de la position du Label : ici on centre
            t_total = self.canevas.create_text(self.pos_X,self.pos_Y,anchor = 'n',text =  unicode(total)+screen.euro , fill = color_debit, font = aFont(30))
            
    def tk_transaction_client(self) :
            self.ensure_tkdisplay()
            #Recuperation des valeur utilses
            solde = self.client.fields["amount"] #acquisition du solde du bracelet
            solde = Configuration.infloat(solde)
            total,bouteilles = self.total_panier(self.panier)
            reste = solde - total
            reste = unicode(reste)

            # solde client
            self.pos_X = (frame_width * 0.3)  #determination en X de la position du Label :
            t_solde = self.canevas.create_text(self.pos_X, self.pos_Y, anchor = 'nw', text = unicode(solde), fill = color_credit, font= aFont(22))

            # symbole screen.euro
            self.euro(t_solde, color=color_credit)
            
            # moins
            width,height,X,Y = self.size (self.t_euro) #calcul des dimensions en pixel du texte/label 
            self.pos_X +=  width #determination en X de la position du Label : 2/5 + t_solde + t_euro
            t_symbole = self.canevas.create_text(self.pos_X, self.pos_Y, anchor = 'nw', text = " - " , fill = color_header, font = aFont(22))
            
            # total du panier
            width,height,X,Y = self.size (t_symbole) #calcul des dimensions en pixel du texte/label : var, type_var
            self.pos_X += width #determination en X de la position du Label : t_solde + t_euro + self.symbole
            t_total = self.canevas.create_text(self.pos_X, self.pos_Y, anchor = "nw", text = unicode(total), fill = color_debit, font=aFont(22))
            
            # symbole screen.euro
            self.euro(t_total)

            #saut de ligne
            self.saut_de_ligne(34)
            t_bouteille = self.canevas.create_text(frame_width*0.5, self.pos_Y, anchor = "n", text = u"("+unicode(bouteilles)+u" produit"+(u"s" if bouteilles>1 else u"")+u")", fill = color_message, font=aFont(18))

            #saut de ligne
            self.saut_de_ligne()
##            
##            # egal
##            self.pos_X = frame_width*0.3 #determination en X de la position du Label            
##            t_symbole = self.canevas.create_text(self.pos_X, self.pos_Y, anchor = 'sw', text = " = " , fill = color_header, font = aFont(18))
##
##            # reste
##            self.sizeX = self.size (t_symbole,"TEXT") #calcul des dimensions en pixel du texte/label : var, type_var
##            self.pos_X += self.sizes[2]-self.sizes[0] #determination en X de la position du Label : t_symbole
##            t_reste = self.canevas.create_text(self.pos_X, self.pos_Y,anchor = 'sw', text = reste, fill = color_credit, font=aFont(30))
##
##            # symbole screen.euro
##            self.euro(t_reste,26,color=color_credit)
                                        
    def tk_vente_bracelets(self,charge) :
            if self.client == None :
                return
                
            self.ensure_tkdisplay()
            if self.qty_choisie < 0 :
                montant = barbaraConfiguration.defaultAmount
            else:
                montant = self.qty_choisie

            if charge :
                # barcode
                self.pos_X = (frame_width-4)/2 #determination en X de la position du Label : ici on centre
                t_barcode = self.canevas.create_text(self.pos_X, self.pos_Y, text = self.client.fields['barcode'], fill = color_client, font = aFont(26))

                #saut de ligne
                self.saut_de_ligne() 

                self.pos_X = frame_width * 0.5 #determination en X de la position du Label : 2/5
                t_montant = self.canevas.create_text(self.pos_X, self.pos_Y, anchor = "center",text = "Montant : " + unicode(montant) + screen.euro, fill = color_header, font = aFont(30))
                    
                #saut de ligne
                self.saut_de_ligne() 

                self.pos_X = frame_width/2  #determination en X de la position du Label : ici on centre
                t_msg = self.canevas.create_text(self.pos_X, self.pos_Y, text = "Cash ou Carte ?" , fill = color_message, font = aFont(20))

                #saut de ligne
                self.saut_de_ligne(45)   

                self.pos_X = frame_width/2  #determination en X de la position du Label : ici on centre
                t_msg = self.canevas.create_text(self.pos_X,self.pos_Y, text = "Annuler ?", fill = color_message, font = aFont(20))
            else:
                self.pos_X = frame_width/2  #determination en X de la position du Label : ici on centre
                t_msg = self.canevas.create_text(self.pos_X, self.pos_Y, text = u"Chargement effectué: " + unicode(montant) + screen.euro , fill = color_header, font = aFont(20))
                
                #saut de ligne
                self.saut_de_ligne()

                self.tk_client(pos_line = self.pos_Y)
                           
    def tk_client(self, pos_line = frame_height/2.5) :
            self.ensure_tkdisplay()
            # barcode
            self.pos_X = frame_width/2 
            self.pos_Y = pos_line
            t_barcode = self.canevas.create_text(self.pos_X, self.pos_Y, text = self.client.fields['barcode'], fill = color_client, font = aFont(26))


            #saut de ligne
            self.saut_de_ligne(40) 
            
            # solde
            self.pos_X = frame_width*0.5
            t_solde = self.canevas.create_text(self.pos_X, self.pos_Y, anchor = 'n',text = self.client.fields["amount"]+screen.euro, fill = color_header, font = aFont(30))

    def tk_produit(self) :
            self.ensure_tkdisplay()
            # nom
            self.pos_X = frame_width/2
            self.pos_Y = frame_height/2.5
            t_produit = self.canevas.create_text(self.pos_X, self.pos_Y, text = self.produit.fields['name'], fill = color_header, font = aFont(26))

            #saut de ligne
            self.saut_de_ligne(40)
            
            # barcode
            self.pos_X = frame_width/2
            t_barcode = self.canevas.create_text(self.pos_X, self.pos_Y,text = self.produit.fields['barcode'], fill  = color_product,font = aFont(26))
            
            #saut de ligne
            self.saut_de_ligne(40)  
                        
            # prix
            self.pos_X = frame_width/2
            t_prix = self.canevas.create_text(self.pos_X, self.pos_Y, text = self.produit.fields['price'], fill = color_debit,font = aFont(30))

            # symbole screen.euro
    ##            self.size(t_prix,"TEXT",1,0 )
    ##            self.pos_X = t_x/2 + self.sizeX/2 #determination en X de la position du Label : ici on centre
            self.euro(t_prix,26)
                        
    def tk_scanner(self) :
            self.ensure_tkdisplay()
            # nom
            self.pos_X = frame_width/2
            self.pos_Y = frame_height/2.5
            t_scanner = self.canevas.create_text(self.pos_X, self.pos_Y, text = self.scanner.id, fill = color_header, font = aFont(20))

            #saut de ligne
            self.saut_de_ligne(40)
            
            # barcode
            self.pos_X = frame_width/2
            t_name = self.canevas.create_text(self.pos_X, self.pos_Y,text = self.scanner.fields['name'], fill  = color_product,font = aFont(26))
            
            #saut de ligne
            self.saut_de_ligne(40)  
                        
            # pin
            self.pos_X = frame_width/2
            t_pin = self.canevas.create_text(self.pos_X, self.pos_Y, text = (u"pin="+self.scanner.fields['pin']), fill = color_debit,font = aFont(26))

            #saut de ligne
            self.saut_de_ligne(40)  
            self.pos_X = frame_width/2
            t_deny = self.canevas.create_text(self.pos_X, self.pos_Y, text = (u"akuino"+self.scanner.fields['client']), fill = color_debit,font = aFont(30))
            #saut de ligne
            self.saut_de_ligne(40)  
            self.pos_X = frame_width/2
            t_deny = self.canevas.create_text(self.pos_X, self.pos_Y, text = self.scanner.strActive(), fill = color_debit,font = aFont(30))
                        
    def tk_utilisateur(self) :
            self.ensure_tkdisplay()
            # nom
            self.pos_X = frame_width/2
            self.pos_Y = frame_height/2.5
            t_utilisateur = self.canevas.create_text(self.pos_X, self.pos_Y, text = self.utilisateur.fields['name'], fill = color_header, font = aFont(26))

            #saut de ligne
            self.saut_de_ligne(40)
            
            # barcode
            self.pos_X = frame_width/2
            t_barcode = self.canevas.create_text(self.pos_X, self.pos_Y,text = self.utilisateur.fields['barcode'], fill  = color_product,font = aFont(26))
                        
            #saut de ligne
            self.saut_de_ligne(40)
            
            self.pos_X = frame_width/2
            t_droits = self.canevas.create_text(self.pos_X, self.pos_Y, text = self.utilisateur.getAccessCode(), fill = color_debit,font = aFont(30))

    def tk_facture(self) :
            self.ensure_tkdisplay()

            theGrid = Tkinter.Canvas(self.canevas, width = frame_width-2, height = frame_height-62, bg=color_canevas, bd=1)
            theGrid.place(anchor=Tkinter.N, x=frame_width/2, y = 60)

            name_column = Tkinter.Label(theGrid,text = "TICKET", fg = color_header, bg = color_canevas,font = aFont(22))
            name_column.grid(row = 0, column = 0,columnspan = 5, pady=4)
            name_column = Tkinter.Label(theGrid,text = "Num.", fg = color_header, bg = color_canevas,font = aFont(20))
            name_column.grid(row = 1, column = 0, pady=2,padx=1)
            name_column = Tkinter.Label(theGrid,text = "Nom", fg = color_header, bg = color_canevas,font = aFont(20))
            name_column.grid(row = 1, column = 1, pady=2,padx=1)
            name_column = Tkinter.Label(theGrid,text = "Qte", fg = color_header,bg = color_canevas,font = aFont(20))
            name_column.grid(row = 1, column = 2, pady=2,padx=1)
            name_column = Tkinter.Label(theGrid,text = " €/u ", fg = color_header,bg = color_canevas,font = aFont(20))
            name_column.grid(row = 1, column = 3, pady=2,padx=1)
            name_column = Tkinter.Label(theGrid,text = " € tot", fg = color_header, bg = color_canevas,font = aFont(20))
            name_column.grid(row = 1, column = 4, pady=2,padx=1)
            for i in range(5):
                theGrid.columnconfigure(i,weight=1)
            ligne = 1
            bouteilles = 0

                
            print "Votre Facture : "
            index = self.debut
            for element in self.prev_panier.keys() [self.debut : self.debut+TAILLE_ECRAN]:
                    ligne += 1
                    
                    #récupération des infos à partir de la base de données

                    #print ("The price of one {} is {} euros \nYou took {} of them" .format(element.fields["name"], element.fields["price"], self.panier[element])) #affichage d'une "Facture"
                                
                    price = element.getCents()/100.0 #on met le prix en float
                
                    #calcul du total
                    total = (price * float(self.prev_panier[element]))
                                                   

                    achat = Tkinter.Label(theGrid,text = unicode(index+1), fg = color_index,bg = color_canevas,font = aFont(14))
                    achat.grid(row = ligne, column = 0, pady=2)
                    achat = Tkinter.Label(theGrid,text = element.fields["name"][:15], fg = color_header,bg = color_canevas,font = aFont(18))
                    achat.grid(row = ligne, column = 1, pady=2)
                    achat = Tkinter.Label(theGrid,text = self.prev_panier[element], fg = color_message,bg = color_canevas,font = aFont(18))
                    bouteilles += self.prev_panier[element]                    
                    achat.grid(row = ligne, column = 2, pady=2)
                    achat = Tkinter.Label(theGrid,text = element.fields["price"], fg = color_message,bg = color_canevas,font = aFont(18))
                    achat.grid(row = ligne, column = 3, pady=2)
                    achat = Tkinter.Label(theGrid,text = total, fg = color_debit,bg = color_canevas,font = aFont(18))
                    achat.grid(row = ligne, column = 4, pady=2)
                    index +=1
            total,bouteilles = self.total_panier(self.prev_panier)
            ligne += 1
            cell = Tkinter.Label(theGrid,text = unicode(len(self.prev_panier)), fg = color_index,bg = color_canevas,font = aFont(18))
            cell.grid(row = ligne, column = 0, pady=2)
            cell = Tkinter.Label(theGrid,text = "TOTAL", fg = color_message,bg = color_canevas,font = aFont(18))
            cell.grid(row = ligne, column = 1, pady=2)
            cell = Tkinter.Label(theGrid,text = unicode(bouteilles), fg = color_message,bg = color_canevas,font = aFont(18))
            cell.grid(row = ligne, column = 2, pady=2)
            cell = Tkinter.Label(theGrid,text = unicode(total), fg = color_debit,bg = color_canevas,font = aFont(18))
            cell.grid(row = ligne, column = 4, pady=2)
    
    def tk_stock(self,all_stock):
            self.ensure_tkdisplay()

            theGrid = Tkinter.Canvas(self.canevas, width = frame_width-2, height = frame_height-62, bg=color_canevas, bd=1)
            theGrid.place(anchor=Tkinter.N, x=frame_width/2, y = 60)

            name_column = Tkinter.Label(theGrid,text = "PRODUITS", fg = color_header, bg = color_canevas,font = aFont(22))
            name_column.grid(row = 0, column = 0,columnspan = 6, pady=4)
            name_column = Tkinter.Label(theGrid,text = "Barcode", fg = color_header, bg = color_canevas,font = aFont(20))
            name_column.grid(row = 1, column = 1, pady=2,padx=4)
            name_column = Tkinter.Label(theGrid,text = "Nom", fg = color_header, bg = color_canevas,font = aFont(20))
            name_column.grid(row = 1, column = 2, pady=2,padx=4)
            name_column = Tkinter.Label(theGrid,text = "€/u", fg = color_header,bg = color_canevas,font = aFont(20))
            name_column.grid(row = 1, column = 3, pady=2,padx=4)
            name_column = Tkinter.Label(theGrid,text = " Qty ", fg = color_header,bg = color_canevas,font = aFont(20))
            name_column.grid(row = 1, column = 4, pady=2,padx=4)
      
            print "Votre Stock : "
            ligne = 5
            if all_stock :
                refset = c.AllProducts.elements.keys()[self.debut : self.debut+TAILLE_ECRAN]
            else:
                refset = [self.produit.id]
            for key in refset:
                objet = c.AllProducts.elements[key]
                ligne += 1
                print objet.fields['barcode'] + " " + objet.fields['name'] + " " + objet.fields['price'] + " " + objet.fields['qty']
                
                produit = Tkinter.Label(theGrid,text = " ABCDEFGHIJKL"[ligne-5], fg = color_header,bg = color_canevas,font = aFont(20))
                produit.grid(row = ligne, column = 0, pady=2,padx=4)
                produit = Tkinter.Label(theGrid,text = objet.fields['barcode'], fg = color_product,bg = color_canevas,font = aFont(16))
                produit.grid(row = ligne, column = 1, pady=2,padx=4)
                produit = Tkinter.Label(theGrid,text = objet.fields['name'][:15], fg = color_header,bg = color_canevas,font = aFont(18))
                produit.grid(row = ligne, column = 2, pady=2,padx=4)
                produit = Tkinter.Label(theGrid,text = objet.fields["price"], fg = color_debit,bg = color_canevas,font = aFont(18))
                produit.grid(row = ligne, column = 3, pady=2,padx=4)
                produit = Tkinter.Label(theGrid,text = objet.fields["qty"], fg = color_message,bg = color_canevas,font = aFont(18))
                produit.grid(row = ligne, column = 4, pady=2,padx=4)
                    
    def tk_collaborateurs(self,all_collabs):
            self.ensure_tkdisplay()

            theGrid = Tkinter.Canvas(self.canevas, width = frame_width-2, height = frame_height-62, bg=color_canevas, bd=1)
            theGrid.place(anchor=Tkinter.N, x=frame_width/2, y = 60)

            name_column = Tkinter.Label(theGrid,text = "COLLABS", fg = color_header, bg = color_canevas,font = aFont(22))
            name_column.grid(row = 0, column = 0,columnspan = 5, pady=4)
            name_column = Tkinter.Label(theGrid,text = "Barcode", fg = color_header, bg = color_canevas,font = aFont(20))
            name_column.grid(row = 1, column = 1, pady=2,padx=4)
            name_column = Tkinter.Label(theGrid,text = "Nom", fg = color_header, bg = color_canevas,font = aFont(20))
            name_column.grid(row = 1, column = 2, pady=2,padx=4)
            name_column = Tkinter.Label(theGrid,text = "Accès", fg = color_header,bg = color_canevas,font = aFont(20))
            name_column.grid(row = 1, column = 3, pady=2,padx=4)
      
            print "Vos collaborateurs : "
            ligne = 5
            if all_collabs :
                refset = c.AllUsers.elements.keys()[self.debut : self.debut+TAILLE_ECRAN]
            else:
                refset = [self.utilisateur.id]
            for key in refset:
                objet = c.AllUsers.elements[key]
                ligne += 1
                print objet.fields['barcode'] + " " + objet.fields['name'] + " " + objet.fields['access']
                
                produit = Tkinter.Label(theGrid,text = " ABCDEFGHIJKL"[ligne-5], fg = color_header,bg = color_canevas,font = aFont(20))
                produit.grid(row = ligne, column = 0, pady=2,padx=4)
                produit = Tkinter.Label(theGrid,text = objet.fields['barcode'], fg = color_product,bg = color_canevas,font = aFont(16))
                produit.grid(row = ligne, column = 1, pady=2,padx=4)
                produit = Tkinter.Label(theGrid,text = objet.fields['name'][:15], fg = color_header,bg = color_canevas,font = aFont(18))
                produit.grid(row = ligne, column = 2, pady=2,padx=4)
                produit = Tkinter.Label(theGrid,text = objet.fields["access"], fg = color_debit,bg = color_canevas,font = aFont(18))
                produit.grid(row = ligne, column = 3, pady=2,padx=4)
        
    def tk_scanners(self,all_scans):
            self.ensure_tkdisplay()

            theGrid = Tkinter.Canvas(self.canevas, width = frame_width-2, height = frame_height-62, bg=color_canevas, bd=1)
            theGrid.place(anchor=Tkinter.N, x=frame_width/2, y = 60)

            name_column = Tkinter.Label(theGrid,text = "SCANNERS", fg = color_header, bg = color_canevas,font = aFont(22))
            name_column.grid(row = 0, column = 0,columnspan = 5, pady=4)
            name_column = Tkinter.Label(theGrid,text = "akuino", fg = color_header, bg = color_canevas,font = aFont(20))
            name_column.grid(row = 1, column = 1, pady=2,padx=4)
            name_column = Tkinter.Label(theGrid,text = "Nom", fg = color_header, bg = color_canevas,font = aFont(20))
            name_column.grid(row = 1, column = 2, pady=2,padx=4)
            name_column = Tkinter.Label(theGrid,text = "PIN", fg = color_header,bg = color_canevas,font = aFont(20))
            name_column.grid(row = 1, column = 3, pady=2,padx=4)
            name_column = Tkinter.Label(theGrid,text = "MAC", fg = color_header, bg = color_canevas,font = aFont(18))
            name_column.grid(row = 1, column = 4, pady=2,padx=4)
      
            print "Vos scanners : "
            ligne = 5
            if all_scans :
                refset = c.AllScanners.elements.keys()[self.debut : self.debut+TAILLE_ECRAN]
            else:
                refset = [self.scanner.id]
            for key in refset:
                objet = c.AllScanners.elements[key]
                ligne += 1
                print objet.id + " " + objet.fields['name'] + " " + objet.fields['pin']
                
                produit = Tkinter.Label(theGrid,text = " ABCDEFGHIJKL"[ligne-5], fg = color_header,bg = color_canevas,font = aFont(20))
                produit.grid(row = ligne, column = 0, pady=2,padx=4)
                produit = Tkinter.Label(theGrid,text = objet.fields["client"], fg = color_debit,bg = color_canevas,font = aFont(18))
                produit.grid(row = ligne, column = 1, pady=2,padx=4)
                produit = Tkinter.Label(theGrid,text = objet.fields['name'][:15], fg = color_header,bg = color_canevas,font = aFont(18))
                produit.grid(row = ligne, column = 2, pady=2,padx=4)
                produit = Tkinter.Label(theGrid,text = objet.fields["pin"], fg = color_debit,bg = color_canevas,font = aFont(18))
                produit.grid(row = ligne, column = 3, pady=2,padx=4)
                produit = Tkinter.Label(theGrid,text = objet.id, fg = color_product,bg = color_canevas,font = aFont(14))
                produit.grid(row = ligne, column = 4, pady=2,padx=4)

    def sauver_utilisateur(self):
        if not self.utilisateur:
            return False
        self.utilisateur.fields["name"] = self.nom_choisi
        if self.qty_choisie and self.qty_choisie >= 0:
            self.utilisateur.setAccessCode(self.qty_choisie)
        self.utilisateur.save(c,self.user)
        return True

    def sauver_produit(self,deny):
        if not self.produit:
            return False
        self.produit.fields["name"] = self.nom_choisi
        if self.qty_choisie and self.qty_choisie >= 0:
            self.produit.setCents(self.qty_choisie)
        if deny:
            self.produit.fields["deny"] = ""
        else:
            self.produit.fields["deny"] = "1"
        self.produit.save(c,self.user)
        return True

    def sauver_scanner(self,destinationHote):
        if not self.scanner:
            return False
        self.scanner.fields["name"] = self.nom_choisi
        if self.qty_choisie and self.qty_choisie >= 0:
            if destinationHote:
                self.scanner.fields["client"] = unicode(self.qty_choisie)
            else:
                self.scanner.fields["pin"] = unicode(self.qty_choisie)
        self.scanner.save(c,self.user)
        return True

    # Ajoute l'argent au bracelet
    def ajouter_argent(self):
        if not self.client:
            return False
        if self.client.fields["sold"] != "yes" :
            ecran_message(self,0, u"!Nouveau Bracelet!")

        if self.qty_choisie < 0 :
            montant = barbaraConfiguration.defaultAmount
        else:
            montant = self.qty_choisie

        if barbaraConfiguration.applicationRole == 'b':
            aBrace = c.client_CreditBrace(self.user.id,self.client.id,float(montant))
            if aBrace:
                c.AllTransactions.total_credit = c.AllTransactions.total_credit + float(montant)
                return True
            else:
                return False
        else:
            c.AllTransactions.credit(self.user,self.client,montant)
            return True

    # Retire l'argent du bracelet
    def retirer_argent(self):
        if not self.client:
            return False
        if barbaraConfiguration.applicationRole == 'b':
            total,bouteilles = self.total_panier(self.panier)
            aBrace = c.client_BuyWithBrace(self.user.id,self.client.id,total,self.panier)
            if aBrace:
                c.AllTransactions.total_buyWithBrace = c.AllTransactions.total_buyWithBrace + float(total)
                return True
            else:
                return False
        else:
            total,bouteilles = self.total_panier(self.panier)
            c.AllTransactions.buyWithBrace(self.user,self.client,total,self.panier)
            return True

    def debiter_carte(self): #TODO:Paiement par Bancontact...
        return False

    # Test du solde du client aussi bien lorsque qu'une transaction est en cours ou non
    # cette foncion retourne plusieurs affichages :
    #       - sans transaction : le panier est donc vide, on affiche le solde du client et son code barre
    #       - transaction en cours : on test son solde : si il est vide, on lui demande de recharger, si il est suffisant pour l'achat, on retourne "ok"
    #           et si il est insufisant, on retourne "possible"
    #       - annulation de transaction, on affiche le solde et le code barre du client afin de vérifier que l'opération n'a pas étée effectuée
    def test_solde (self) :

        if self.mode == CB_Vente_Bracelets :
            if self.client != None:
                return "vente",0
        else :    
            total,bouteilles = self.total_panier(self.panier)
            
            if ((total == 0) and (self.client != None)): #le panier est vide, on a donc pas de client courrant
                solde = self.client.fields["amount"] #acquisition du solde du bracelet
                    
            if total!= 0 : #le panier n'est pas vide, on a donc un client courrant 
                solde = self.client.fields["amount"] #acquisition du solde du bracelet 

            # test du solde et de la solvabilité du client pour la transaction si on a un panier NON-VIDE 
            solde = Configuration.infloat(solde) #on met le solde en float

            if (solde == 0)  : #t n'a rien sur son bracelet
                if total == 0 :
                    #print "solde nul, veuillez recharger"
                    return "nul",0

                else : # total != 0 : #le panier n'est pas vide, on a donc un client courrant ou une opération en cours
                    return "nulle",total
                          
            else :
                if total == 0 : #le panier est vide, on a donc pas de client courrant ou d'opération en cours
                    #print ("Le bracelet {} a encore {} euros".format(self.client.fields["brace"],self.client.fields["amount"]))
                    return "vide",0
                
                else : #le panier n'est pas vide, on a donc un client courrant
                    if solde >= total :
                        return "ok",total
                    else :
                        return "possible",total

    # Mise à jour du panier, on incrémente ou remplace la quantité d'un produit déjà présent dans le panier ou si il n'y est pas, on l'ajoute avec la quantité choisie / par défaut
    def ajouter_produit(self):  
        
        if ((self.produit != None) ) :
            
            if self.produit in self.panier :    #si le produit est déjà dans le panier :                
                if self.qty_choisie == -1 :    # ou on incrémente la quantité présente
                    self.panier[self.produit] += 1
                else:
                    self.panier[self.produit] = self.qty_choisie
                if self.panier[self.produit] <= 0:
                    del self.panier[self.produit]
            else :
                if self.qty_choisie == -1 :
                    self.panier[self.produit] = 1
                else:
                    self.panier[self.produit] = self.qty_choisie
            self.prev_panier = self.panier
                
            #print self.panier
            #print self.liste_panier
            self.setQty(-1)

    # Permet de retirer un  produit du panier en le scannant : un scan = -1 ou bien de remplacer la quantité déjà présente
    def retirer_produit(self) :        
        if ((self.produit != None) ) :
            
            if self.produit in self.panier :    #si le produit est déjà dans le panier :
                if self.qty_choisie == -1 :    # ou on décrémente la quantité présente
                    self.panier[self.produit] -= 1
                else:
                    self.panier[self.produit] = self.qty_choisie
                if self.panier[self.produit] <= 0:
                    del self.panier[self.produit]
                self.prev_panier = self.panier
                self.setQty(-1)                    
            else :
                ecran_message(self,0,u"Ce produit n'est pas présent",u"dans le panier !", u"Pour l'ajouter,", u"re-scannez le mode :",u'"Ventes de produits"')
                self.produit = None
               
            
    # Calcul du prix total du panier         
    def total_panier(self, panier):
        total = 0
        bouteilles = 0
        for element in panier :
            #récupération des infos à partir de la base de données
            #qty = self.produit.fields["qty"] #acquisition de la quantité dans la base de donnée
            
            price = element.getCents()/100.0
            
            #calcul du total
            total += (price * float(panier[element]))
            bouteilles += panier[element]
        #print total
        return total,bouteilles
            
    # Première fonction de la classe : celle-ci récupère le code barre dans la queue et l'envoie dans la fonction barcode_interpreter
    def run_ounce(self):
        global screen
        try:
            res = self.inputQueue.get(False)
            if res:
                #print res+"**"
                if hardConf.running: # Processing en cours!
                    PIG.write(hardConf.running, 0)
                try:
                    self.barcode_interpreter(res)

                    y = 0
##                    if not screen.devConnected and not bluetooth.pairing:
##                          if hardConf.oled:
##                              screen.draw.text((4,y+1), u"Bluetooth Pairing", font=screen.font,fill=255)
##                              y += screen.lineHeight
##                          bluetooth.pairingDevice()
##                          if bluetooth.startScan:
##                              screen.devConnected += "*"
##                          if hardConf.oled:
##                              screen.show(screen.devConnected)
##                    elif bluetooth.startScan:
##                          screen.devConnected += "*"
                    self.close_tkdisplay()
                    time.sleep(0.01)
                except:
                    traceback.print_exc()
                    
                if hardConf.running:
                    PIG.write(hardConf.running, 1)
        except:
            #print self.rank
            pass

    def command_interpreter(self,res):

        try :
            if (self.user != None) :
                #determination du mode
                    if res in modes :                    # il faudra tester si l'utilisateur peut accéder à ce mode
                        
                        if res == CB_User_Cancel :
                            self.reinit(None)
                            ecran_message(self,0,u"!Veuillez vous identifier")
                        else:
                            if res == CB_Vente_Bracelets:
                                if self.user.allowed('b'):
                                    self.reinit(self.user, res)                    
                                    ecran_message(self,0,u"!Nouveau bracelet: ",u"Choisir le montant",u"à ajouter sur le bracelet.", u"Par défaut : "+unicode(barbaraConfiguration.defaultAmount)+" euros",u" ",\
                                                   u"!Bracelet déjà vendu: ",u"Recharge,",u"Solde", u"ou Remboursement")
                                    self.pref_qty = u"€ "
                                    self.pref_nom = u""
                            elif res == CB_Vente_Produits:
                                if self.user.allowed('c'):
                                    self.reinit(self.user, res)                    
                                    ecran_message(self,0,u"Scanner les ventes",u"puis le bracelet",u"du client")
                                    self.pref_qty = u"Qte="
                                    self.pref_nom = u""
                            elif res == CB_Stock:
                                if self.user.allowed('g'):
                                    self.reinit(self.user, res)                    
                                    ecran_message(self,0,u"!Produits",u"!et Services",u"!disponibles")
                                    self.pref_qty = u"Cents="
                                    self.pref_nom = u"Nom:"
                            elif res == CB_Collabs:
                                if self.user.allowed('g'):
                                    self.reinit(self.user, res)                    
                                    ecran_message(self,0,u"!Collaborateurs",u"et privilèges")
                                    self.pref_qty = u"Priv."
                                    self.pref_nom = u"Nom:"
                            elif res == CB_Gestion:
                                if self.user.allowed('g'):
                                    self.reinit(self.user, res)                    
                                    ecran_message(self,0,u"!Commandes de configuration...",u"IP="+localAddr,u"Batt.="+unicode(lastBatt)+u"V")
                                    self.pref_qty = u""
                                    self.pref_nom = u""
                            elif res == CB_Scanners:
                                if self.user.allowed('g'):
                                    self.reinit(self.user, res)                    
                                    ecran_message(self,0,u"!Scanners environnants")
                                    self.pref_qty = u"akuino#"
                                    self.pref_nom = u"Nom:"

                        return True
                    elif res in actions :
                        action = res
                        if (action == CB_Arbitraire):
                            self.arbitraire = True
                            ecran_message(self,0,u"Veuillez scanner le",u"!code-barre",u"!à utiliser")
                        elif (action == CB_Modifier):
                            if self.mode == CB_Gestion:
                                if not self.nom_choisi or (len(self.nom_choisi) != 11) or not self.nom_choisi[:6].isnumeric() or not self.nom_choisi[7:].isnumeric():
                                    ecran_message(self,0,u"Changer DATE HEURE",u"6chiffr espace 4chiffr:",u"!AAMMJJ HHMM",u"Ex.171231 2359")
                                else:
                                    print u"Setting clock to "+self.nom_choisi
                                    exec_command(self,[u'sudo',u'date',u'+"'+MANUAL_TIME_FORMAT+u'"','-s',u'"'+self.nom_choisi+u'"'])
                                    ecran_message(self,0,u"DATE HEURE",u"!"+self.nom_choisi,u"inscrite.")
                            elif self.mode == CB_Vente_Bracelets:
                                self.modifier = True
                            elif self.mode == CB_Vente_Produits:
                                self.modifier = True
                            elif self.mode == CB_Collabs:
                                print "Desactiver Collab"
                                if self.utilisateur:
                                    self.utilisateur.setInactive()
                                    if self.sauver_utilisateur():
                                        ecran_utilisateur(self)
                                    else:
                                        ecran_message(self,0,u"!Problème de réseau?",u"Désactiver Utilisateur",u"annulé")
                                        self.partial_init()
                            elif self.mode == CB_Stock:
                                print "Desactiver Produit"
                                if self.produit:
                                    self.produit.setInactive()
                                    if self.sauver_produit(True):
                                        ecran_produit(self)
                                    else:
                                        ecran_message(self,0,u"!Problème de réseau?",u"Déscativer Produit",u"annulé")
                                        self.partial_init()
                            elif self.mode == CB_Scanners:
                                print "Desactiver Scanner"
                                if self.scanner:
                                    self.scanner.setInactive()
                                    self.qty_choisie = 2 # Hote impossible: scanner desactive
                                    if self.sauver_scanner(True):
                                        ecran_scanner(self)
                                    else:
                                        ecran_message(self,0,u"Désactiver Scanner",u"annulé")
                                        self.partial_init()
                        elif (action == CB_Effacer_Nombre):
                            self.setQty(-1)
                            ecran_qty(self)
                        elif (action == CB_Generer):
                            if self.mode == CB_Vente_Bracelets:
                                generer_bracelet(self)
                            elif self.mode == CB_Stock:
                                generer_produit(self)
                            elif self.mode == CB_Collabs:
                                generer_utilisateur(self)
                        elif (action == CB_Initialiser):
                            if self.mode == CB_Vente_Bracelets:
                                ecran_sync_printer(self)
                            elif self.mode == CB_Collabs:
                                #TODO Confirmation puis VIDER le fichier des utilisateurs?
                                pass
                            elif self.mode == CB_Stock:
                                #TODO Confirmation puis VIDER le fichier des produits?
                                pass
                            elif self.mode == CB_Scanners:
                                #TODO Détruire tous les DENY et refaire un SCAN complet du réseau Bluetooth pour creer des Scanners "denied"
                                pass
                            elif self.mode == CB_Gestion:
                                if exec_command(self,["git","-C","..","pull"]):
                                    ecran_message(self,0,u"!BARBARA est",u"!mise à jour.",u"Redémarrer pour",u"bénéficier des",u"améliorations")
                                else:
                                    ecran_message(self,0,u"!ERREUR à la mise à jour",u"!de BARBARA.")
                        elif action == CB_Precedent:
                            self.debut -=  TAILLE_ECRAN
                            if self.mode == CB_Vente_Produits:
                                ecran_facture(self)
                            elif self.mode == CB_Stock:
                                ecran_stock(self,True)
                            elif self.mode == CB_Collabs:
                                ecran_collaborateurs(self,True)
                            elif self.mode == CB_Scanners:
                                ecran_scanners(self,True)
                        elif action == CB_Suivant :
                            self.debut +=  TAILLE_ECRAN
                            if self.mode == CB_Vente_Produits:
                                ecran_facture(self)
                            elif self.mode == CB_Stock:
                                ecran_stock(self,True)
                            elif self.mode == CB_Collabs:
                                ecran_collaborateurs(self,True)
                            elif self.mode == CB_Scanners:
                                ecran_scanners(self,True)
                        elif action == CB_Cash :
                            if self.mode == CB_Vente_Bracelets:
                                print "Paiement CASH"
                                if self.ajouter_argent():
                                    ecran_vente_bracelets(self,False)
                                    self.qty_choisie = -1
                                else:
                                    ecran_message(self,0,u"!Problème de réseau?",u"Transaction annulée")
                                    self.partial_init()
                            elif self.mode == CB_Collabs:
                                print "Sauver info Collab"
                                if self.sauver_utilisateur():
                                    ecran_utilisateur(self)
                                else:
                                    ecran_message(self,0,u"!Problème de réseau?",u"Modif.Utilisateur annulée")
                                    self.partial_init()
                            elif self.mode == CB_Stock:
                                print "Sauver info Produit"
                                if self.sauver_produit(False):
                                    ecran_produit(self)
                                else:
                                    ecran_message(self,0,u"!Problème de réseau?",u"Modif.Produit annulée")
                                    self.partial_init()
                            elif self.mode == CB_Scanners:
                                print "Sauver info Scanner"
                                if self.sauver_scanner(True): # Qtite = Hote
                                    ecran_scanner(self)
                                else:
                                    ecran_message(self,0,u"Modif.Scanner annulée")
                                    self.partial_init()
                        elif action == CB_Carte :
                            if self.mode == CB_Vente_Bracelets:
                                if self.debiter_carte():  # TODO                            
                                    if self.ajouter_argent():
                                        ecran_vente_bracelets(self,False)
                                        self.qty_choisie = -1
                                    else:
                                        ecran_message(self,0,u"!Problème de réseau?",u"Transaction annulée")
                                        self.partial_init()
                                else:
                                    ecran_message(self,0,u"Transaction annulée")
                                    self.partial_init()
                            elif self.mode == CB_Scanners:
                                print "Sauver info Scanner"
                                if self.sauver_scanner(False): #Qtite = PIN
                                    ecran_scanner(self)
                                else:
                                    ecran_message(self,0,u"Modif.Scanner annulée")
                                    self.partial_init()
                        elif (action == CB_Shutdown):
                            if self.mode == CB_Gestion:
                                SHUT_NOW(self)
                        return True
                    elif res in menu_choices :
                            aChoice = menu_choices[res] - 1 # Choix numéroté à partir de 1
                            if self.mode == CB_Stock:
                                self.produit = self.syncChoix(aChoice,c.AllProducts.elements)
                                if self.produit:
                                    self.nom_choisi = self.produit.fields["name"]
                                    self.setQty(self.produit.getCents())
                                    ecran_produit(self)
                            elif self.mode == CB_Collabs:
                                self.utilisateur = self.syncChoix(aChoice,c.AllUsers.elements)
                                if self.utilisateur:
                                    self.nom_choisi = self.utilisateur.fields["name"]
                                    self.setQty(self.utilisateur.getAccessCode())
                                    ecran_utilisateur(self)
                            elif self.mode == CB_Scanners:
                                self.scanner = self.syncChoix(aChoice,c.AllScanners.elements)
                                if self.scanner:
                                    self.nom_choisi = self.scanner.fields["name"]
                                    self.setQty(self.scanner.fields["client"])
                                    ecran_scanner(self)
                            return True
        except :
            traceback.print_exc()
        return False
        

    # Ici, on détermine la catégorie du code barre et on lance les fonctions correspondantes
    def barcode_interpreter(self,res) :
        if self.arbitraire:
            self.arbitraire = False
            if (res >= "1000000000000") and (res <= "1000999999999"):
                ecran_message(self,0,u"!Les codes-barre",u"commençant par 1000",u"!ne sont pas autorisés")
            else:
                if self.mode == CB_Stock:
                    self.produit = c.AllProducts.assignObject(res,None)
                    if self.produit == None:
                        ecran_message(self,0,u"!Code-barre",res,u"!déjà utilisé.")
                    else:
                        self.nom_choisi = self.produit.fields["name"]
                        self.setQty(self.produit.getCents())
                        ecran_produit(self)
                elif self.mode == CB_Collabs:
                    self.utilisateur = c.AllUsers.assignObject(res,None)
                    if self.utilisateur == None:
                        ecran_message(self,0,u"!Code-barre",res,u"!déjà utilisé.")
                    else:
                        self.nom_choisi = self.utilisateur.fields["name"]
                        self.setQty(self.utilisateur.getAccessCode())
                        ecran_utilisateur(self)
                elif self.mode == CB_Vente_Bracelets:
                    self.client = c.AllBraces.assignObject(res,None)
                    if self.client == None:
                        ecran_message(self,0,u"!Code-barre",res,u"!déjà utilisé.")
                    else:
                        ecran_vente_bracelets(self,True)
                else:
                    self.partial_init()
            return
    
        try :
            
            if self.user != None :
                if self.command_interpreter(res):
                    return
                
            # If client/server, ensure the barcode is categorised
            currObject = c.ensureBarcode(res)
            #print (res+"=>"+ (unicode(currObject) if currObject!=None else "None") )             

            if currObject == None:
                ecran_message(self,0,res+u":",u"!Code barre inconnu",u"ou",u"!Erreur du Réseau")
                return
            elif isinstance(currObject,Configuration.User):
                if self.user and (self.mode == CB_Collabs):
                    self.utilisateur = currObject
                    self.nom_choisi = self.utilisateur.fields["name"]
                    self.setQty(self.utilisateur.getAccessCode())
                    ecran_utilisateur(self)
                    return
                else:
                    #determination de l'utilisateur
                    for local_rank in allContexte:
                        aContext = allContexte[local_rank]
                        if aContext and aContext.rank != self.rank :
                            if aContext.user == currObject:
                                ecran_message(aContext,0,"",u"!Vous êtes passé",u"!à un autre scanner!")
                                aContext.close_tkdisplay()
                                aContext.reinit(None)
                    print (currObject.fields["name"] + " is connected with : " + unicode(self.rank))
                    
                    self.reinit(currObject)
                    acc = currObject.access()
                    if acc == 'g':
                        ecran_message(self,0,u"Veuillez choisir: ","!Vente Bracelets,","!Vente Produits,","!ou Gestion")
                    elif acc == 'a' or acc == 'g':
                        ecran_message(self,0,u"Veuillez choisir: ","!Vente Bracelets,","!ou Vente Produits")
                    elif acc == 'b':
                        self.command_interpreter(CB_Vente_Bracelets)
                    elif acc == 'c':
                        self.command_interpreter(CB_Vente_Produits)
                    else:
                        ecran_message(self,0,u"Accès interdit")
                    return
                

            if (self.user == None) :
                ecran_message(self,0,u"!Veuillez vous identifier")
                return
            #un utilisateur est connecté
            elif isinstance(currObject,Configuration.Braces) :
                
                self.client = currObject
               
                if (self.mode == CB_Vente_Produits and (self.client.fields["sold"] == "yes") and (self.panier)) :  # un utilisateur est connecté,le panier n'est pas vide, il n'y a pas encore de transaction en cours  
                    #self.ajouter_produit()                                      # Séquence  1) on scane les produits 
                    print (self.client.fields["barcode"] + " pris en charge")      #           2) une fois les produits scannés et SEULEMENT self.clientès, on scane le client
                    solvabilite,total = self.test_solde()
                    if solvabilite == "nulle" :
                        ecran_message(self,0,u"Veuillez aller charger",u"votre bracelet.", u"!Vente annulée")
                        self.tk_client(pos_line = self.pos_Y)
                        self.partial_init()
                    elif solvabilite == "possible" :
                        ecran_message(self,0,u"!Solde insuffisant", u"Retirer des articles",u"ou tout annuler ?")
                        self.tk_client(pos_line = self.pos_Y)
                        #affichage du solde + demande si on retire des articles ou si on annule tout
                    elif solvabilite == "ok" :
                        self.modifier = False
                        ecran_transaction_client(self)
                        self.retirer_argent()
                        self.tk_client(pos_line = self.pos_Y)
                        self.partial_init()

                elif(self.mode == CB_Vente_Bracelets):
                    ecran_vente_bracelets(self,True)                            
                elif not self.panier and (self.client.fields["sold"] == "yes"):
                    self.test_solde()
                    ecran_client(self)
                    self.client = None
                    
                elif self.client.fields["sold"] == "no" :
                    ecran_message(self,0,(u"Ce bracelet n'a pas encore"), (u"été vendu."),(u"Aucune transaction ou "),(u"opération possible !"),(u""))
                    
                    self.client = None

            #determination du produit
            elif isinstance(currObject,Configuration.Products):

                self.produit = currObject

                if self.mode == CB_Stock :
                    ecran_produit(self)
                    self.nom_choisi = self.produit.fields["name"]
                    self.setQty(self.produit.getCents())

                    
                elif self.mode == CB_Vente_Produits :
                    #print c.AllProducts.elements[res]

                    if self.modifier:
                        self.retirer_produit()                    
                    else:
                        self.ajouter_produit()
                    ecran_vente_produits(self)

                else :  
                    ecran_produit(self)
                    #print c.AllProducts.elements[res].fields["name"] + " : " + c.AllProducts.elements[res].fields["price"] + screen.euro
                    self.produit = None

            elif isinstance(currObject,Configuration.Qty):

                if (self.mode == None) :
                    pass
                elif not self.charge: #n'aura d'impact et d'intérêt que lorsque l'on sera dans la vente de bracelet
                        # cette condition permet de bloquer le changement de la quantité sans l'accord du client car l'opération necesitera une annulation des opérations en cours
                    val = currObject.fields["number"]
                    if not val: # pas normal
                        return
                    elif val.isnumeric():
                        val = int(val)

                        # Test des variables dizaines et unites pour les remettre à zero
                        if (val > 999999): # trop grand
                            return
                        elif (val == 999999): #Clear 100000
                            self.z5 = 0
                        elif (val == 99999): #Clear 10000
                            self.z4 = 0
                        elif (val == 9999): #Clear 1000
                            self.z3 = 0
                        elif (val >= 9032) and (val < 9127):
                            self.nom_choisi = self.nom_choisi+chr(val-9000)
                        elif val == 9127: # DEL
                            if self.nom_choisi:
                                self.nom_choisi = self.nom_choisi[:-1]
                        elif val == 9128: # CLEAR
                            self.nom_choisi = u""
                        elif (val >= 9129) and (val < (9129 + len(accented)) ):
                            self.nom_choisi = self.nom_choisi+accented[val-9129]
                        elif (val == 999): #Clear 100
                            self.z2 = 0
                        elif (val == 99): #Clear 10
                            self.z1 = 0
                        else :
                            if val >= 100000 :
                                self.z5 = val
                            elif val >= 10000 :
                                self.z4 = val
                            elif val >= 1000 :
                                self.z3 = val
                            elif val >= 100 :
                                self.z2 = val
                            elif val >= 10 :
                                self.z1 = val
                            else :
                                self.unite = val
                        self.qty_choisie = self.unite + self.z1 + self.z2 + self.z3 + self.z4 + self.z5
                        if self.mode == CB_Vente_Produits:
                            self.produit = None # plus de produit courant si on entre une quantité
                    else:
                        print (unicode(val)+": valeur incorrecte")
                        return
                    ecran_qty(self)
                else :
                    #print "Montant non modifiable, veuillez annuler l'operation et recommencer !"
                    ecran_message(self,0,u"Montant/Quantité non modifiable",u"Veuillez annuler l'opération",u"et recommencer")
                    
        except :
            traceback.print_exc()
            
for contextRank in range(MAX_TILES):
    allContexte[contextRank] = None

rank = 0

def insureContext(aScannerKey):
    global rank
    
    aScanner = c.AllScanners.elements[aScannerKey]
    if aScanner.isActive():
        for contextRank in range(MAX_TILES):
            if allContexte[contextRank] and allContexte[contextRank].currScanner and allContexte[contextRank].currScanner == aScanner:
                return allContexte[contextRank]
        # not found
        if rank < MAX_TILES:
            allContexte[rank] = Contexte(rank, aScannerKey)
            contextRank = rank
            rank += 1
            return allContexte[contextRank]
        else:
            print(aScannerKey+" TOO MANY SCANNERS: 6 is the maximum")
            return None
    else:
        return None
    
threadBlueTooth,threadBluetoothEnQueue = bluetooth.start()

# classe qui lance un thread de gestion du code barre par appareil, cette fonction se charge aussi de mettre les codes barres receuillis dans une queue
class InputEventThread(threading.Thread):

    def __init__(self,currentScanner):
        threading.Thread.__init__(self)
        self.currScanner = currentScanner
        self.dev = evdev.InputDevice("/dev/input/event"+unicode(self.currScanner.numDev))
        self.Alive = False
        
    def run(self):
        self.Alive = True
        try:
            self.dev.grab()
            print(self.dev.fn+u" grabbed !")
        except IOError as anError:
            self.Alive = False
            traceback.print_exc()
            try:
                self.dev.ungrab()
                print (self.dev.fn++u" ungrabbed")
            except:
                pass
            return

        time.sleep(0.01)
                
        global Alive

        res=""
        while Alive and self.Alive:
           caps=False
           try:
               for event in self.dev.read():
                    #print event
                    if not Alive:
                        break
                    if not self.Alive:
                        break
                    if event.type == evdev.ecodes.EV_KEY:
                        data = evdev.categorize(event)
                        if data.scancode == 42:
                            caps = not data.keystate == 0
                        elif data.keystate == 1:
                            if data.scancode == 28:
                                local_rank = -1
                                for contextRank in range(MAX_TILES):
                                    if allContexte[contextRank] and allContexte[contextRank].currScanner and allContexte[contextRank].currScanner == self.currScanner:
                                        local_rank = contextRank
                                        break
                                if local_rank >= 0:
                                    print("\n " + unicode(local_rank) + ":  " + res)
                                    contexte = allContexte[local_rank]
                                    contexte.inputQueue.put(res+"")
                            
                                res = ""

                            else:
                                #print(data.scancode)
                                try:
                                    if caps:
                                        res += capscodes[int(data.scancode)]
                                    else:
                                        res += scancodes[int(data.scancode)]
                                except:
                                    print("Invelid key:",data.scancode)
                                    
                    #else:
                       # print event               
           except io.BlockingIOError :
                print ("Blocking")
                time.sleep(0.01)
           except IOError as anError:
                if anError.errno == 11:
                    #print (self.dev.fn,anError)
                    time.sleep(0.001)
                elif anError.errno == 19:
                    try:
                        self.dev.ungrab()
                        print ("ungrabbed 19")
                    except:
                        pass
                    break
                else:
                    traceback.print_exc()
                    try:
                        self.dev.ungrab()
                        print (u"ungrabbed, error IOerror")
                    except:
                        pass
                    break
           except:
                traceback.print_exc()
                try:
                    self.dev.ungrab()
                    print ("ungrabbed other")
                except:
                    pass
                break
           time.sleep(0.001)
        self.Alive = False


def InputListThread():
    global screen
    global Alive
    global bluetoothScanner
    
# UTILISER /proc/bus/input/devices
    physical = None
    looping = 0
    while Alive:
     looping += 1
     if ((looping % 8) == 0) or screen.newConnect:
      with screen.lock:
        looping = 0
        screen.newConnect = False
        somethingDisplayed = False
        try:
            fInputDevices = open("/proc/bus/input/devices",'r')
            activeSet = []
            screen.devConnected = ""
            for inputLine in fInputDevices:
                if inputLine[:8] == 'U: Uniq=':
                    physical = inputLine[8:].strip()
                elif inputLine[:12] == 'H: Handlers=':
                    for capab in inputLine[12:].strip().split(' '):
                        if capab[:5] == 'event':
                            numDev = int(capab[5:])
                            if physical:
                                key = c.AllScanners.makeKey(physical)
                                if key in c.AllScanners.elements:
                                    currScanner = c.AllScanners.elements[key]                                
                                    if currScanner.isActive(): #not denied
                                        currScanner.numDev = numDev
                                        currScanner.paired = True
                                        currScanner.connected = True
                                        key = currScanner.id
                                        threadContext = insureContext(key)
                                        if threadContext:
                                            activeSet.append(key)
                                            screen.devConnected += unicode(threadContext.rank)
                                            if currScanner.reader is None :
                                                currScanner.reader = InputEventThread(currScanner)
                                            elif (not currScanner.reader.is_alive()) or (not currScanner.reader.Alive):
                                                currScanner.reader = InputEventThread(currScanner)
                                            else:
                                                continue # Thread still alive
                                            currScanner.reader.start()

                                            if hardConf.oled:
                                                if not somethingDisplayed:
                                                    screen.refreshDisplay = datetime.datetime.now() + datetime.timedelta(seconds=6)
                                                    screen.draw.rectangle((screen.begScreen,0,screen.endScreen,63),fill=0)
                                                    screen.linePos = 0
                                                    strnow = screen.refreshDisplay.strftime("%H:%M")
                                                    screen.draw.text((screen.begScreen,screen.linePos+1), strnow, font=screen.font,fill=255)
                                                    screen.linePos += screen.lineHeight
                                                    somethingDisplayed = True
                                                screen.draw.text((screen.begScreen,screen.linePos+1), "Connect "+unicode(currScanner.id), font=screen.font,fill=255)
                                                screen.linePos += screen.lineHeight
                                                screen.draw.text((screen.begScreen,screen.linePos+1), "            "+currScanner.id, font=screen.font,fill=255)
                                                screen.linePos += screen.lineHeight
                                    physical = None

            for key in c.AllScanners.elements:
                currScanner = c.AllScanners.elements[key]
                if key in activeSet:
                    pass
                else:
                    if currScanner.reader:
                        currScanner.reader.Alive = False
                    if currScanner.connected and (not currScanner.last or ((currScanner.last+datetime.timedelta(seconds=30)) < datetime.datetime.now()) ):
                        bluetooth.addDisconnect(currScanner)
                if currScanner.isActive() and not currScanner.connected:
                    bluetooth.addTodo(currScanner)
            if somethingDisplayed:
                screen.show(screen.devConnected)
                time.sleep(0.01)
        except:
            traceback.print_exc()
##      if not screen.devConnected and not bluetooth.pairing:
##          if hardConf.oled:
##              screen.draw.text((4,screen.linePos+1), u"Bluetooth Pairing", font=screen.font,fill=255)
##              screen.linePos += screen.lineHeight
##          bluetooth.pairingDevice()
##          if bluetooth.startScan:
##              screen.devConnected += "*"
##          if hardConf.oled:
##              screen.show(screen.devConnected)
##      elif bluetooth.startScan:
##          screen.devConnected += "*"
      time.sleep(0.1) # TODO: was 2 !            

threadList = threading.Thread(target=InputListThread)
threadList.daemon = True
threadList.start()

ADCconf = 0x98+hardConf.battery_port

class ADCDACPi:

    # variables
    __adcrefvoltage = 3.3  # reference voltage for the ADC chip.

    # Define SPI bus and init
    if hardConf.battery == 'SPI':
        spiADC = spidev.SpiDev()
        spiADC.open(0, 0)
        spiADC.max_speed_hz = (900000)


    def read_adc_voltage(self, channel, mode):
        """
        Read the voltage from the selected channel on the ADC
         Channel = 1 or 2
        """
        if ((channel > 2) or (channel < 1)):
            print 'ADC channel needs to be 1 or 2'
        if ((mode > 1) or (mode < 0)):
            print 'ADC mode needs to be 0 or 1. 0 = Single Ended, 1 = Differential'
        raw = self.read_adc_raw(channel, mode)
        voltage = (self.__adcrefvoltage / 4096) * raw
        return voltage

    def read_adc_raw(self, channel, mode):
        # Read the raw value from the selected channel on the ADC
        # Channel = 1 or 2
        if ((channel > 2) or (channel < 1)):
            print 'ADC channel needs to be 1 or 2'
        if ((mode > 1) or (mode < 0)):
            print 'ADC mode needs to be 0 or 1. 0 = Single Ended, 1 = Differential'
        if (mode == 0):            
            r = self.spiADC.xfer2([1, (1 + channel) << 6, 0])
            ret = ((r[1] & 0x0F) << 8) + (r[2])
        if (mode == 1):
            if (channel == 1):            
                r = self.spiADC.xfer2([1, 0x00, 0])
            else:
                r = self.spiADC.xfer2([1, 0x40, 0])
            ret = ((r[1]) << 8) + (r[2])
        return ret

    def set_adc_refvoltage(self, voltage):
        """
        set the reference voltage for the analogue to digital converter.
        The ADC uses the raspberry pi 3.3V power as a voltage reference so
        using this method to set the reference to match the
        exact output voltage from the 3.3V regulator will increase the
        accuracy of the ADC readings.
        """
        if (voltage >= 0.0) and (voltage <= 7.0):
            __adcrefvoltage = voltage
        else:
            print 'reference voltage out of range'
        return

def SHUT_NOW(contexte):
    global Alive
    global bluetooth
    if contexte:
        ecran_message(contexte,0,"!ON FERME TOUT!")
    Alive = False
    bluetooth.alive = False
    time.sleep(2.5)
    os.system(hardConf.battery_shutdown)

def tension():

    global Alive
    global stats_label
    global lastBatt

    if hardConf.battery:
        try:
                if hardConf.battery == 'I2C':
                    #bus_pi = I2C.get_i2c_device(hardConf.battery_address, busnum=hardConf.i2c_bus)
                    bus_pi = SMBus(hardConf.i2c_bus)
                    print bus_pi
                elif hardConf.battery == 'SPI':
                    bus_pi = ADCDACPi()  # create an instance of the ADCDAC Pi with a DAC gain set to 1

                    # set the reference voltage.  this should be set to the exact voltage
                    # measured on the raspberry pi 3.3V rail.
                    bus_pi.set_adc_refvoltage(3.3)
        
                while Alive:
                                    
                    #os.system("i2cset -y 1 0x6E 0x98")
                    time.sleep(20)

                    if hardConf.battery == 'I2C':

                        #bus_pi.write_byte(ADCaddr,0x98)# va charger la valeur du registre
                                                    # dans le mcp
                        """print 'ADC I2C:',hex(addr)"""
                        #xa = bus_pi.read_word_data(ADCaddr,0)# recupère la valeur en décimal
                        xa = bus_pi.read_i2c_block_data(hardConf.battery_address,ADCconf,3)
                        if len(xa) < 2:
                            continue
                        x1 = xa[0] # les 2 premier Bytes et les 2 derniers doivent                    
                        x2 = xa[1] # être inversé pour récupérer la bonne valeur
                        #x1b = int(x1,16)*256                
                        #x2b = int(x2,16)
                        tens = (x1*256) + x2
                        if tens == 32767:
                            continue   #TODO: Implanter la bonne synchronisation avec l'arrivee du résultat...
                        elif tens >=32768:
                            tens = tens - 65536
                        tens = (tens*0.0625)/1000 # 0.0625 codé sur 16 bits
                                                  # et /1000 pour avoir la valeur en volt
                    elif hardConf.battery == 'SPI':
                        tens = bus_pi.read_adc_voltage(1, 0)
                    tens= tens*hardConf.battery_divider # 9.4727 est le coefficient du pont diviseur de
                                          # tension qui est placé au borne de l'ADC
                    tens = round(tens, 2) # Arrondi la valeur au centième près

                    if tens < 4:
                        print ("Sous tension: "+unicode(tens))
                        pass
                    else:
                        lastBatt = tens
                        if tens <= hardConf.battery_breakout_volt:
                            stats_label.set(unicode(tens)+u"V : ATTENTION")
                            print (tens+"V lower than "+unicode(hardConf.battery_breakout_volt)+"...")
                            time.sleep(5)
                            if hardConf.battery == 'I2C':
                                bus_pi.write_byte(hardConf.battery_address,ADCconf)
                                xa = bus_pi.read_i2c_block_data(hardConf.battery_address,0)
                                if len(xa) < 3:
                                    continue
                                x = hex(xa) 
                                x1 = x[4:6]                    
                                x2 = x[2:4]
                                tens = (x1*256) + x2
                                if tens >=32768:
                                    tens = tens - 65536
                                tens = (tens*0.0625)/1000
                            elif hardConf.battery == 'SPI':
                                tens = bus_pi.read_adc_voltage(1, 0)
                            tens= tens*hardConf.battery_divider
                            tens = round(tens, 2)
                            if tens < hardConf.battery_breakout_volt:
                                stats_label.set(unicode(tens)+u"V : HALTE DU SYSTEME")
                                print(tens+"V : Shutdown...")
                                SHUT_NOW(None)
                        else:  
                            print 'Sensor battery: '+unicode(tens)+' V'

        except:
                traceback.print_exc()
                    
threadADC = threading.Thread(target=tension)
threadADC.daemon = True
threadADC.start()


aSecond = datetime.timedelta(seconds=1)

def keypadCheck():

    global Alive
    
    begdigit = None
    if hardConf.shutdown:
        PIG.set_mode(hardConf.shutdown, pigpio.INPUT)
        PIG.set_pull_up_down(hardConf.shutdown, pigpio.PUD_UP)
    kp = None
    if hardConf.keypad:
        kp = keypad(hardConf.keypad_r,hardConf.keypad_c)
    while Alive:
        closing = False
        if hardConf.keypad:
           digit = kp.getKey()
           if digit == 11:
                closing = True
                Alive = False
        if hardConf.shutdown:
            digit = PIG.read(hardConf.shutdown)
            if digit == 0:
                closing = True
        if closing:
            now = datetime.datetime.now()
            if not begdigit:
                begdigit = now
            elif (now - begdigit) > aSecond:
                Alive = False
                if hardConf.battery_shutdown:
                   SHUT_NOW(None)
        else:
            begdigit = None
        time.sleep(0.05)

threadKEYS = threading.Thread(target=keypadCheck)
threadKEYS.daemon = True
threadKEYS.start()

def configPanel(event):
    print "Bienvenue dans le panneau de configuration"

def execThreads():

    global Alive
    
    time.sleep(0.01)
    for local_rank in allContexte:
        aContext = allContexte[local_rank]
        if aContext:
            aContext.run_ounce()
    if Alive:
        tkdisplay_root.after(100, execThreads )
    else:
        tkdisplay_root.destroy()

try:
    entree = Tkinter.Entry(tkdisplay_root)
    entree.bind("<Return>", configPanel)
    entree.focus_set()
    entree.place()

    if hardConf.running:
        PIG.write(hardConf.running, 1)
    #execThreads()
    tkdisplay_root.after(100, execThreads )
    tkdisplay_root.mainloop()

except:
    traceback.print_exc()
    syslog.syslog(syslog.LOG_ERR, u"BARBARA avorte...")

Alive = False
bluetooth.alive = False
time.sleep(0.5)
threadList.join()
time.sleep(0.5)
#if hardConf.running:
#    PIG.write(hardConf.running, 0)
PIG.stop()

# COMMANDE DE lANCEMENT DU PROGRAMME : sudo xinit ~/Desktop/mypython.sh
