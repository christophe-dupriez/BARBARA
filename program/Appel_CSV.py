#!/usr/bin/env python
# -*- coding: utf-8 -*-
import csv
import os
import time
import traceback

def FichierCSV():
    
    try: #si le fichier existe
        if(open('Braces.csv')):
           with open('Client.csv', 'a') as csvfile:
            DiF1 = ['Client', 'CB', 'Time', 'Solde']
            writer = csv.DictWriter(csvfile, fieldnames=DiF1, delimiter = '\t')
    except: #si le fichier n'existe pas
        with open('Braces.csv', 'w') as csvfile:
            DiF1 = ['Client', 'CB', 'Time', 'Solde']
            writer = csv.DictWriter(csvfile, fieldnames=DiF1, delimiter = '\t')
            writer.writeheader()

    try: #si le fichier existe
        if(open('Products.csv')):
           with open('Products.csv', 'a') as csvfile:
            DiF1 = ['Produit', 'CB', 'Prix', 'Qty']
            writer = csv.DictWriter(csvfile, fieldnames=DiF1, delimiter = '\t')
    except: #si le fichier n'existe pas
        with open('Products.csv', 'w') as csvfile:
            DiF1 = ['Produit', 'CB', 'Prix', 'Qty']
            writer = csv.DictWriter(csvfile, fieldnames=DiF1, delimiter = '\t')
            writer.writeheader()

    try: #si le fichier existe
        if(open('Users.csv')):
           with open('Users.csv', 'a') as csvfile:
            DiF1 = ['User', 'CB', 'Time']
            writer = csv.DictWriter(csvfile, fieldnames=DiF1, delimiter = '\t')
    except: #si le fichier n'existe pas
        with open('Users.csv', 'w') as csvfile:
            DiF1 = ['User', 'CB', 'Time']
            writer = csv.DictWriter(csvfile, fieldnames=DiF1, delimiter = '\t')
            writer.writeheader()

   
