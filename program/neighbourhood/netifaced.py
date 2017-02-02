import netifaces
for ifaceName in netifaces.interfaces():
    addresses = [i['addr'] for i in netifaces.ifaddresses(ifaceName).setdefault(netifaces.AF_INET, [{'addr':'No IP addr'}] )]
    print '%s: %s' % (ifaceName, ', '.join(addresses))
