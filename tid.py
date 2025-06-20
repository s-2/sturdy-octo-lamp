import json

# available from https://www.gs1.org/docs/epc/mdid_list.json
mdids = json.load(open('mdid_list.json', 'r'))


def print_mdid(tid_hex):
    if len(tid_hex) == 0:
        # raise ValueError("empty TID")
        return

    firstwords = int(tid_hex[:8], 16)

    tmdid = (firstwords & 0x001FF000) >> 12
    tmn = firstwords & 0x00000FFF

    for md in mdids['registeredMaskDesigners']:
        if md['mdid'] == '{:09b}'.format(tmdid):
            # if verbose print("found mdid", tmdid)
            print(md['manufacturer'])
            if 'chips' in md:
                for chip in md['chips']:
                    if chip['tmnBinary'] == '{:012b}'.format(tmn):
                        print(chip['modelName'])
                        if 'productUrl' in chip:
                            print(chip['productUrl'])
                        break
            break


