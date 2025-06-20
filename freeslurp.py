dumps = """1306100505001840FF01E1BCFE925404	mpg
1306C0020500032046B5E003085Df021	efteling
1307800205300240C3000494C2716003	chessington
13061005050018415701E1BD5671A003	thirdfill
1306100505004940000021BC00000000	new_act
13061005050049415701E1BD56702C01	new_1stfill
1304700205301F41410000153EAAAC01	thorpe mardi gras
13047002053019415EB800155E8C6801	thorpe park
1305700205300D400000249400000000 	alton towers
1307800205300240C3000494C2716003 	chessington
1300E00204F05D40E2000002D37E0803	Disney 100"""



venues_10 = {0x04: 'Royal Caribbean', \
             0x14: 'Universal Studios Orlando', \
             0x1F: 'Legoland Florida', \
             0x47: 'Thorpe Park', \
             0x50: 'Rulantica', \
            }

venues_13 = {0x0E: 'Walt Disney Orlando', \
             0x47: 'Thorpe Park', \
             0x57: 'Alton Towers', \
             0x61: 'Movie Park Germany', \
             0x6C: 'Efteling', \
             0x78: 'Chessington', \
            }

moviepark_locations = {0b000: 'Western Snack (left)', \
                       0b001: 'Snack Attack (left)', \
                       0b010: 'Snack Attack (right) or Hollywood Snack', \
                       0b011: 'Western Snack (right)', \
                       0b101: '(former Snack Attack right?)', \
                      }

class cup:
    def __init__(self, epc_hex, name=None):
        self.epc = int(epc_hex, 16)
        self.name = name

    def get(self, msb, lsb):
        """read value of bit field given by start and end positions"""
        size = msb - lsb
        if size < 0:
            raise ValueError("field msb must be greater than lsb")
        mask = (2 ** size - 1) << lsb
        #print(msb, lsb)
        #print("mask:", mask)
        return (self.epc & mask) >> lsb

    def parse(self):
        """parse freestyle cup for region 0x13 (0x10 currently unsupported)"""
        region = self.get(128, 120) # 0x13 global, 0x10 US (?)
        venue = self.get(120, 108)
        mystery0 = self.get(108, 80) # cup size & material? (20oz; cold drinks only etc.)
        offer_id = self.get(80, 70)
        mystery1 = self.get(70, 65) # always 00000
        valid_mm = self.get(65, 61)
        valid_dd = self.get(61, 56) # valid day + 1
        mystery2 = self.get(56, 46) # always 0000 0001 11 (after first fill)
        mystery3 = self.get(46, 38) # always 10 0001 10 (when cup received)
        wait_min = self.get(38, 33)
        lastfill_mm = self.get(33, 29)
        lastfill_dd = self.get(29, 24)
        lastfill_hh = self.get(24, 19)
        lastfill_min = self.get(19, 13)
        fill_location = self.get(13, 10)
        fill_left = self.get(10, 5)
        fill_cnt = self.get(5, 0)

        print("offer # {:03x}".format(offer_id))
        print("wait", wait_min)
        print("valid until: {:02d}-{:02d}".format(valid_mm, valid_dd))
        print("Last fill: {:02d}-{:02d} {:02d}:{:02d} ({} times, {} left)".format(lastfill_mm, lastfill_dd, lastfill_hh, lastfill_min, fill_cnt, fill_left))

        loc_string = ""
        if venue in venues_13:
            loc_string += venues_13[venue] 
            if venue == 0x61 and fill_location in moviepark_locations and fill_cnt:   # Movie Park Germany
                loc_string += " - " + moviepark_locations[fill_location]
        
        print("location: {:03b} ".format(fill_location) + loc_string)
        print()


if __name__ == '__main__':
    for dump in dumps.splitlines():
        epc, descr = dump.split("\t")
        print(epc, descr)
        cup(epc).parse()



