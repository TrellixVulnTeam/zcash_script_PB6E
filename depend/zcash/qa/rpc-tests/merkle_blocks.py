#!/usr/bin/env python3
# Copyright (c) 2014-2016 The Bitcoin Core developers
# Copyright (c) 2016-2022 The Zcash developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or https://www.opensource.org/licenses/mit-license.php .

#
# Test merkleblock fetch/validation
#

import string
from test_framework.test_framework import BitcoinTestFramework
from test_framework.authproxy import JSONRPCException
from test_framework.util import assert_equal, assert_raises, \
    start_node, connect_nodes


class MerkleBlockTest(BitcoinTestFramework):

    def __init__(self):
        super().__init__()
        self.cache_behavior = 'clean'
        self.num_nodes = 4

    def setup_network(self):
        self.nodes = []
        # Nodes 0/1 are "wallet" nodes
        self.nodes.append(start_node(0, self.options.tmpdir, ["-debug"]))
        self.nodes.append(start_node(1, self.options.tmpdir, ["-debug"]))
        # Nodes 2/3 are used for testing
        self.nodes.append(start_node(2, self.options.tmpdir, ["-debug"]))
        self.nodes.append(start_node(3, self.options.tmpdir, ["-debug", "-txindex"]))
        connect_nodes(self.nodes[0], 1)
        connect_nodes(self.nodes[0], 2)
        connect_nodes(self.nodes[0], 3)

        self.is_network_split = False
        self.sync_all()

    def run_test(self):
        print("Mining blocks...")
        self.nodes[0].generate(105)
        self.sync_all()

        chain_height = self.nodes[1].getblockcount()
        assert_equal(chain_height, 105)
        assert_equal(self.nodes[1].getbalance(), 0)
        assert_equal(self.nodes[2].getbalance(), 0)

        node0utxos = self.nodes[0].listunspent(1)
        tx1 = self.nodes[0].createrawtransaction([node0utxos.pop()], {self.nodes[1].getnewaddress(): 10})
        txid1 = self.nodes[0].sendrawtransaction(self.nodes[0].signrawtransaction(tx1)["hex"])
        tx2 = self.nodes[0].createrawtransaction([node0utxos.pop()], {self.nodes[1].getnewaddress(): 10})
        txid2 = self.nodes[0].sendrawtransaction(self.nodes[0].signrawtransaction(tx2)["hex"])
        assert_raises(JSONRPCException, self.nodes[0].gettxoutproof, [txid1])

        self.nodes[0].generate(1)
        blockhash = self.nodes[0].getblockhash(chain_height + 1)
        self.sync_all()

        txlist = []
        blocktxn = self.nodes[0].getblock(blockhash, True)["tx"]
        txlist.append(blocktxn[1])
        txlist.append(blocktxn[2])

        assert_equal(self.nodes[2].verifytxoutproof(self.nodes[2].gettxoutproof([txid1])), [txid1])
        assert_equal(self.nodes[2].verifytxoutproof(self.nodes[2].gettxoutproof([txid1, txid2])), txlist)
        assert_equal(self.nodes[2].verifytxoutproof(self.nodes[2].gettxoutproof([txid1, txid2], blockhash)), txlist)

        txin_spent = self.nodes[1].listunspent(1).pop()
        tx3 = self.nodes[1].createrawtransaction([txin_spent], {self.nodes[0].getnewaddress(): 10})
        self.nodes[0].sendrawtransaction(self.nodes[1].signrawtransaction(tx3)["hex"])
        self.nodes[0].generate(1)
        self.sync_all()

        txid_spent = txin_spent["txid"]
        txid_unspent = txid1 if txin_spent["txid"] != txid1 else txid2

        # We can't find the block from a fully-spent tx
        assert_raises(JSONRPCException, self.nodes[2].gettxoutproof, [txid_spent])
        # ...but we can if we specify the block
        assert_equal(self.nodes[2].verifytxoutproof(self.nodes[2].gettxoutproof([txid_spent], blockhash)), [txid_spent])
        # ...or if the first tx is not fully-spent
        assert_equal(self.nodes[2].verifytxoutproof(self.nodes[2].gettxoutproof([txid_unspent])), [txid_unspent])
        try:
            assert_equal(self.nodes[2].verifytxoutproof(self.nodes[2].gettxoutproof([txid1, txid2])), txlist)
        except JSONRPCException:
            assert_equal(self.nodes[2].verifytxoutproof(self.nodes[2].gettxoutproof([txid2, txid1])), txlist)
        # ...or if we have a -txindex
        assert_equal(self.nodes[2].verifytxoutproof(self.nodes[3].gettxoutproof([txid_spent])), [txid_spent])

        # Quick test of getblock using blockhash and different levels of verbosity
        result = self.nodes[0].getblock(blockhash, 2)
        coinbase_txid = result["tx"][0]["txid"]
        result = self.nodes[0].getblock(blockhash, 1)
        assert_equal(coinbase_txid, result["tx"][0])  # verbosity 1 only lists txids
        result = self.nodes[0].getblock(blockhash, 0)
        assert(c in string.hexdigits for c in result) # verbosity 0 returns raw hex

        # Test getblock heights including negatives relative to the head
        assert_equal(self.nodes[0].getblock("0")["height"], 0)
        assert_raises(JSONRPCException, self.nodes[0].getblock, ["108"])
        assert_equal(self.nodes[0].getblock("107")["height"], 107)
        assert_equal(self.nodes[0].getblock("-1")["height"], 107)
        assert_equal(self.nodes[0].getblock("-2")["height"], 106)
        assert_equal(self.nodes[0].getblock("-20")["height"], 88)
        assert_equal(self.nodes[0].getblock("-107")["height"], 1)
        assert_equal(self.nodes[0].getblock("-108")["height"], 0)
        assert_raises(JSONRPCException, self.nodes[0].getblock, ["-109"])
        assert_raises(JSONRPCException, self.nodes[0].getblock, ["-0"])

        # Test getblockhash negative heights
        assert_equal(self.nodes[0].getblockhash(-1), self.nodes[0].getblockhash(107))
        assert_equal(self.nodes[0].getblockhash(-2), self.nodes[0].getblockhash(106))

if __name__ == '__main__':
    MerkleBlockTest().main()
