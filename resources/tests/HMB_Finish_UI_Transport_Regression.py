"""Offline Finish UI clocks, target CAS and replay protection; no execution."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parent))
from HMB_Finish_Look_Multishot_Regression import m, node, catalog, select, edit


def wire(n):
    n._restore_widget_parameter(live=False)
    return copy.deepcopy(m._raw_parameter(n, m.WIDGET_PARAMETER_NAME))


def request(n, operation="edit", *, sequence=1, client="client-a", clock=None, number=None, brightness=None):
    if operation != "refresh" and client not in getattr(n, "_hmb_finish_ui_clients", {}):
        n._apply_widget_value(request(n, "refresh", client=client))
    if operation != "refresh":
        sequence += 1
    value = copy.deepcopy(n._widget_state)
    if number is not None:
        value["shot"] = {"channel_uuid": "channel", **catalog()["shots"][number-1]}
    if brightness is not None:
        value["finish_look"]["beauty"].update(enabled=True, brightness=brightness)
    clock = copy.deepcopy(clock or wire(n)[m.UI_TRANSPORT_KEY])
    key = n._hmb_finish_key(value["shot"]["channel_uuid"], value["shot"]["shot_uuid"])
    value[m.UI_TRANSPORT_KEY] = {"schema": m.UI_TRANSPORT_SCHEMA, "version": 1,
        "operation": operation, "session_id": clock["session_id"], "base_revision": clock["revision"],
        "base_target_revision": clock["target_revisions"].get(key, 0),
        "client_id": client, "client_epoch": getattr(n,"_hmb_finish_ui_clients",{}).get(client,{}).get("client_epoch", ""),
        "request_id": f"{client}-{sequence}", "sequence": sequence}
    return value


class FinishTransport(unittest.TestCase):
    def setUp(self):
        self.guard=patch.object(socket, "create_connection", side_effect=AssertionError("External networking forbidden"))
        self.guard.start()
    def tearDown(self):self.guard.stop()

    def test_optional_transport_is_not_creative_state_or_prompt(self):
        n=node();value=wire(n)
        self.assertEqual(len(n._widget_state),9);self.assertEqual(len(value),10)
        self.assertEqual(m.validate_widget_state(value),n._widget_state)
        self.assertNotIn(m.UI_TRANSPORT_KEY,n._hmb_finish_look_shot_snapshot_for(channel_uuid="channel",shot_uuid="uuid-1"))
        self.assertNotIn(m.UI_TRANSPORT_KEY,m._raw_parameter(n,m.SHOT_STORE_PARAMETER_NAME))
        self.assertEqual(m.compile_finish_look_prompt(value["finish_look"]),m.compile_finish_look_prompt(n._last_valid_state))

    def test_refresh_is_read_only_and_echoes_exact_request(self):
        n=node();value=request(n,"refresh")
        before=copy.deepcopy((n._widget_state,n._last_valid_state,n._hmb_finish_documents,dict(n.parameter_output_values)))
        with patch.object(m,"compile_finish_look_prompt",side_effect=AssertionError("Refresh compiled")):
            n._apply_widget_value(value)
        self.assertEqual((n._widget_state,n._last_valid_state,n._hmb_finish_documents,dict(n.parameter_output_values)),before)
        ack=wire(n)[m.UI_TRANSPORT_KEY]
        self.assertEqual((ack["status"],ack["client_id"],ack["request_id"],ack["sequence"]),("refreshed","client-a","client-a-1",1))

    def test_target_cas_applies_once_and_old_sequence_never_replays(self):
        n=node();first=request(n,brightness=1.5);n._apply_widget_value(first)
        applied=copy.deepcopy((n._last_valid_state,n._remote_revision,n._hmb_finish_documents))
        n._apply_widget_value(first)
        self.assertEqual((n._last_valid_state,n._remote_revision,n._hmb_finish_documents),applied)
        self.assertEqual(wire(n)[m.UI_TRANSPORT_KEY]["status"],"duplicate")
        newer=request(n,sequence=3,brightness=2);n._apply_widget_value(newer)
        n._apply_widget_value(request(n,sequence=2,brightness=.5))
        self.assertEqual(n._last_valid_state["beauty"]["brightness"],2)
        self.assertEqual(wire(n)[m.UI_TRANSPORT_KEY]["status"],"stale_sequence")

    def test_sibling_remote_change_does_not_discard_user_edit(self):
        n=node();old_clock=wire(n)[m.UI_TRANSPORT_KEY]
        value=request(n,clock=old_clock,brightness=1.5)
        n._hmb_apply_finish_remote_for(channel_uuid="channel",shot_uuid="uuid-4",request={"schema":m.REMOTE_SCHEMA,"version":1,"request_id":"remote-sibling","base_revision":0,"changes":{"beauty":{"enabled":True,"brightness":2}}})
        n._apply_widget_value(value)
        ack=wire(n)[m.UI_TRANSPORT_KEY]
        self.assertEqual(ack["status"],"accepted");self.assertGreater(ack["revision"],old_clock["revision"])
        self.assertEqual(n._last_valid_state["beauty"]["brightness"],1.5)
        self.assertEqual(n._hmb_finish_look_shot_snapshot_for(channel_uuid="channel",shot_uuid="uuid-4")["finish_look_state"]["beauty"]["brightness"],2)

    def test_same_target_conflict_and_remote_lock_do_not_apply(self):
        n=node();old=request(n,brightness=1.5)
        edit(n,2);n._apply_widget_value(old)
        self.assertEqual(wire(n)[m.UI_TRANSPORT_KEY]["status"],"conflict")
        self.assertEqual(n._last_valid_state["beauty"]["brightness"],2)
        n._remote_connected=True;n._restore_widget_parameter(live=False)
        n._apply_widget_value(request(n,sequence=2,brightness=.5))
        self.assertEqual(wire(n)[m.UI_TRANSPORT_KEY]["status"],"remote_locked")
        self.assertEqual(n._last_valid_state["beauty"]["brightness"],2)
        language=request(n,sequence=3);language["language"]="en";n._apply_widget_value(language)
        self.assertEqual(n._widget_state["language"],"en");self.assertEqual(wire(n)[m.UI_TRANSPORT_KEY]["status"],"accepted")

    def test_selection_only_reads_target_and_inactive_edit_keeps_view(self):
        n=node();select(n,4);edit(n,1.5);select(n,1)
        n._apply_widget_value(request(n,"select",number=4,brightness=2))
        self.assertEqual(n._last_valid_state["beauty"]["brightness"],1.5)
        active=copy.deepcopy(n._last_valid_state);outputs=copy.deepcopy(dict(n.parameter_output_values))
        n._apply_widget_value(request(n,sequence=2,number=1,brightness=2))
        self.assertEqual(n._widget_state["shot"]["shot_uuid"],"uuid-4")
        self.assertEqual(n._last_valid_state,active);self.assertEqual(dict(n.parameter_output_values),outputs)
        self.assertEqual(n._hmb_finish_look_shot_snapshot_for(channel_uuid="channel",shot_uuid="uuid-1")["finish_look_state"]["beauty"]["brightness"],2)

    def test_session_reload_legacy_values_and_old_session_rejection(self):
        n=node();edit(n,1.5);old=wire(n);old_command=request(n,brightness=2)
        restored=m.HMBFinishLookLibrary(name="Reloaded Finish")
        restored.set_parameter_value(m.WIDGET_PARAMETER_NAME,old,initial_setup=True)
        restored.set_parameter_value(m.SHOT_STORE_PARAMETER_NAME,copy.deepcopy(m._raw_parameter(n,m.SHOT_STORE_PARAMETER_NAME)),initial_setup=True)
        restored._hmb_reconcile_shot_routing(catalog())
        self.assertNotEqual(wire(restored)[m.UI_TRANSPORT_KEY]["session_id"],old[m.UI_TRANSPORT_KEY]["session_id"])
        restored._apply_widget_value(old_command)
        self.assertEqual(wire(restored)[m.UI_TRANSPORT_KEY]["status"],"stale_session")
        self.assertEqual(restored._last_valid_state["beauty"]["brightness"],1.5)
        legacy=copy.deepcopy(restored._widget_state);legacy["finish_look"]["beauty"]["brightness"]=.5
        restored._apply_widget_value(legacy);self.assertEqual(restored._last_valid_state["beauty"]["brightness"],.5)

    def test_deleted_target_and_deleted_node_cannot_apply(self):
        n=node();value=request(n,number=4,brightness=2)
        reduced=catalog();reduced["shots"]=reduced["shots"][:3];reduced["generation"]+=1
        base={key:reduced[key] for key in ("channel_uuid","generation","shots")};reduced["metadata_sha256"]=m._canonical_sha256(base)
        n._hmb_reconcile_shot_routing(reduced);n._apply_widget_value(value)
        self.assertEqual(wire(n)[m.UI_TRANSPORT_KEY]["status"],"target_unavailable")
        n._node_deleted=True;before=copy.deepcopy((n._widget_state,dict(n.parameter_values),dict(n.parameter_output_values)))
        n._apply_widget_value(request(n,sequence=2,brightness=2))
        self.assertEqual((n._widget_state,dict(n.parameter_values),dict(n.parameter_output_values)),before)

    def test_native_before_set_preserves_command_but_validator_drops_it(self):
        n=node();value=request(n,brightness=1.5)
        parameter=type("Parameter",(),{"name":m.WIDGET_PARAMETER_NAME})()
        normalized=n.before_value_set(parameter,value)
        self.assertEqual(normalized[m.UI_TRANSPORT_KEY],value[m.UI_TRANSPORT_KEY])
        self.assertNotIn(m.UI_TRANSPORT_KEY,m.validate_widget_state(normalized))

    def test_bounded_client_leases_reject_evicted_wire_and_inactive_remote_lock(self):
        n=node();old=request(n,brightness=1.5)
        for index in range(m.MAX_UI_CLIENTS+1):n._apply_widget_value(request(n,"refresh",client=f"other-{index}"))
        self.assertEqual(len(n._hmb_finish_ui_clients),m.MAX_UI_CLIENTS)
        n._apply_widget_value(old);self.assertEqual(wire(n)[m.UI_TRANSPORT_KEY]["status"],"stale_client")
        self.assertFalse(n._last_valid_state["beauty"]["enabled"])
        select(n,4);n._remote_connected=True;n._restore_widget_parameter(live=False)
        n._apply_widget_value(request(n,client="new-editor",number=1,brightness=2))
        self.assertEqual(wire(n)[m.UI_TRANSPORT_KEY]["status"],"remote_locked")
        self.assertFalse(n._hmb_finish_look_shot_snapshot_for(channel_uuid="channel",shot_uuid="uuid-1")["finish_look_state"]["beauty"]["enabled"])

    def test_command_arriving_during_previous_reply_is_not_dropped(self):
        n=node();first=request(n,brightness=1.5);triggered=[]
        parameter=type("Parameter",(),{"name":m.WIDGET_PARAMETER_NAME})()
        def publish(name,value):
            if name!=m.WIDGET_PARAMETER_NAME or value[m.UI_TRANSPORT_KEY]["status"]!="accepted" or triggered:return
            triggered.append(True)
            second=request(n,sequence=2,brightness=.5,clock=value[m.UI_TRANSPORT_KEY])
            n.after_value_set(parameter,n.before_value_set(parameter,second))
        n.publish_update_to_parameter=publish
        n.after_value_set(parameter,n.before_value_set(parameter,first))
        self.assertEqual(triggered,[True]);self.assertEqual(n._last_valid_state["beauty"]["brightness"],.5)
        self.assertEqual(wire(n)[m.UI_TRANSPORT_KEY]["request_id"],"client-a-3")


def run_browser_bridge():
    """Production Python methods over stdio; fixtures never open a socket."""
    socket.create_connection=lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError("External networking forbidden"))
    n=None
    for line in sys.stdin:
        try:
            message=json.loads(line);kind=message.get("kind")
            if kind=="reset":
                n=node()
                for number in range(1,6):select(n,number);edit(n,number/2)
                select(n,1)
            elif kind=="request":
                parameter=type("Parameter",(),{"name":m.WIDGET_PARAMETER_NAME})()
                value=n.before_value_set(parameter,message["payload"])
                n.after_value_set(parameter,value)
            elif kind=="remote":
                number=message["number"];key=n._hmb_finish_key("channel",f"uuid-{number}")
                doc=n._hmb_finish_current_document() if key==n._hmb_finish_active_key else n._hmb_finish_documents.get(key,{})
                n._hmb_apply_finish_remote_for(channel_uuid="channel",shot_uuid=f"uuid-{number}",request={"schema":m.REMOTE_SCHEMA,"version":1,"request_id":message.get("id",f"remote-{number}-{doc.get('remote_revision',0)}"),"base_revision":doc.get("remote_revision",0),"changes":{"beauty":{"enabled":True,"brightness":message["brightness"]}}})
            elif kind=="lock":n._remote_connected=message["locked"]
            elif kind=="delete":
                value=catalog();value["shots"]=[row for row in value["shots"] if row["number"]!=message["number"]];value["generation"]+=1
                for index,row in enumerate(value["shots"],1):row["number"]=index
                value["metadata_sha256"]=m._canonical_sha256({key:value[key] for key in ("channel_uuid","generation","shots")})
                n._hmb_reconcile_shot_routing(value)
            elif kind!="read":raise AssertionError("Unknown fixture message")
            output={"ok":True,"value":wire(n),"snapshots":{row["shot_uuid"]:n._hmb_finish_look_shot_snapshot_for(channel_uuid="channel",shot_uuid=row["shot_uuid"]) for row in n._widget_state["shot_catalog"].get("shots",[])}}
        except Exception as error:output={"ok":False,"error":str(error)}
        print(json.dumps(output,ensure_ascii=True),flush=True)


if __name__=="__main__":
    if "--bridge" in sys.argv:run_browser_bridge()
    else:unittest.main(verbosity=2)
