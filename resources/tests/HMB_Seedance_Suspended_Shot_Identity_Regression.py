"""Real callback AST: temporary Source loss cannot silently reassign a Generator."""
from __future__ import annotations
import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT=Path(__file__).resolve().parents[2]
tree=ast.parse((ROOT/'HMBSeedanceGeneration.py').read_text('utf-8'))
cls=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='HMBSeedanceGeneration')
names={'_hmb_clear_shot_routing_catalog','_hmb_reconcile_shot_routing',
       '_hmb_reconcile_replacement_shot_routing','_hmb_other_seedance_shot_claims'}
methods={node.name:node for node in cls.body if isinstance(node,ast.FunctionDef) and node.name in names}
assert set(methods)==names
routing=SimpleNamespace(_same_flow_nodes=lambda node:('synthetic',node.siblings))
scope={'Any':Any,'deepcopy':deepcopy,'_shot_routing':routing,'SHOT_AUTOCLAIM_ENABLED_PARAMETER':'autoclaim'}
exec(compile(ast.Module(body=list(methods.values()),type_ignores=[]),str(ROOT/'HMBSeedanceGeneration.py'),'exec'),scope)

class Node:
    def __init__(self):
        self.identity={'channel_uuid':'original-channel','shot_uuid':'shot-3'}
        self._hmb_shot_catalog_snapshot=None;self.siblings=[];self.choices=[]
    def _shot_identity(self):return deepcopy(self.identity)
    def _validate_shot_catalog_snapshot(self,value):return deepcopy(value)
    def _set_seedance_shot_choices(self,labels):self.choices=labels
    def _hmb_available_seedance_shot_catalog(self,snapshot):return deepcopy(snapshot) if snapshot else {}
    def get_parameter_value(self,name):return name=='autoclaim'
    def _apply_seedance_shot_selection(self,requested,*,fallback_to_available):
        snapshot=self._hmb_shot_catalog_snapshot
        shots=snapshot['shots'] if snapshot else []
        selected=next((row for row in shots if row['shot_uuid']==requested),None)
        if not selected and fallback_to_available and shots:selected=shots[0]
        self.identity={'channel_uuid':snapshot['channel_uuid'] if selected else '',
                       'shot_uuid':selected['shot_uuid'] if selected else ''}
    def _hmb_shot_channel_subscription(self):
        return dict(participant_kind='seedance',enabled=bool(self.identity['shot_uuid']),**self.identity)
    def _reconcile_shared_shot_routing(self,*,strict):assert strict

for name in names:setattr(Node,name,scope[name])
def catalog(channel,order=('shot-1','shot-3','shot-2','shot-4','shot-5')):
    return dict(channel_uuid=channel,generation=1,metadata_sha256='a'*64,
        shots=[dict(shot_uuid=uid,number=index+1,name='Named '+uid) for index,uid in enumerate(order)])

node=Node();node._hmb_clear_shot_routing_catalog()
assert node.identity=={'channel_uuid':'','shot_uuid':''}
assert node._hmb_suspended_shot_identity=={'channel_uuid':'original-channel','shot_uuid':'shot-3'}
# Repeated cleanup must not erase the original exact identity.
node._hmb_clear_shot_routing_catalog()
node._hmb_reconcile_shot_routing(catalog('temporary-standalone-picker'))
assert not node.identity['shot_uuid'],'A temporary Picker channel must not borrow this Generator'
node._hmb_reconcile_shot_routing(catalog('original-channel'))
assert node.identity=={'channel_uuid':'original-channel','shot_uuid':'shot-3'}
assert node._hmb_suspended_shot_identity is None
# Reservations prevent a new generator taking an absent existing owner's UUID.
other=Node();other._hmb_clear_shot_routing_catalog();node.siblings=[node,other]
assert node._hmb_other_seedance_shot_claims('original-channel')=={('original-channel','shot-3')}
assert node._hmb_other_seedance_shot_claims('foreign-channel')==set()
other._hmb_node_deleted=True
assert node._hmb_other_seedance_shot_claims('original-channel')==set()
# Router-proven new ImageAsset replacement remains available with new UUIDs.
fresh=Node();fresh._hmb_clear_shot_routing_catalog()
fresh._hmb_reconcile_replacement_shot_routing(catalog('explicit-new-image',('new-1','new-2')))
assert fresh.identity=={'channel_uuid':'explicit-new-image','shot_uuid':'new-1'}
assert fresh._hmb_suspended_shot_identity is None
print('HMB Seedance suspended Shot identity: PASS (renumber-safe exact restore; no temporary Picker rebind; repeat cleanup; reserved UUID; foreign and deleted claims; new Image replacement)')
