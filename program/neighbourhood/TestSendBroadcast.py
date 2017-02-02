from __future__ import absolute_import, division, print_function, unicode_literals

# Send UDP broadcast packets

import socket
import sys
import time

DEFAULT_PORT = 1248

def send_broadcast(port, msg=None):
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  s.bind(('', 0))
  s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

  while 1:
    data = msg or (repr(time.time()) + '\n')
    s.sendto(data, ('<broadcast>', port))
    time.sleep(2)

if __name__ == '__main__':
  import netifaces
  for ifaceName in netifaces.interfaces():
      addresses = [i['addr'] for i in netifaces.ifaddresses(ifaceName).setdefault(netifaces.AF_INET, [{'addr':'No IP addr'}] )]
      IP = ', '.join(addresses)
      #print '%s: %s' % (ifaceName, str(IP))
      if (ifaceName != 'lo'):
        if (IP != 'No IP addr'):
          localAddr = IP

  send_broadcast(DEFAULT_PORT,"BARBARA "+unicode(localAddr)+":"+unicode(DEFAULT_PORT))
