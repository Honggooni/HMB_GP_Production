from __future__ import annotations

import base64
import copy
import importlib.util
import pickle
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]


def load_picker():
    path = ROOT / "HMBVideoPickerLibrary.py"
    spec = importlib.util.spec_from_file_location(
        "hmb_video_picker_real_saved_workflow_replay",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


picker = load_picker()


# Exact HMB_PICKER_STATE pickle extracted from the production Griptape workflow
# wingtest_b.py after Browse imported one MP4 into ImageAsset Shot 1. Keeping the
# real 123-field shape catches lifecycle defects hidden by minimal synthetic
# fixtures (notably the previous-process writer/runtime identity quartet).
_REAL_SAVED_PICKLE_B64 = (
    "gASVHyMAAAAAAAB9lCiMBnNjaGVtYZSMF21heWEtdmlkZW8tcGlja2VyLXN0YXRllIwOc3RhdGVfcmV2aXNpb26USwaMDHN0YXRl"
    "X3dyaXRlcpSMBnB5dGhvbpSMGndyaXRlcl9ydW50aW1lX2luc3RhbmNlX2lklIwcMjBmYmExZDAzODAtMThjZGE5Y2IwZGI5ODE4"
    "NJSMG3dyaXRlcl9saWZlY3ljbGVfZ2VuZXJhdGlvbpRLAYwVc3RhdGVfcHVibGlzaGVkX2F0X21zlIoGn9qsIaABjBZmcm9udGVu"
    "ZF9zZWVuX3JldmlzaW9ulEsAjAtzY2VuZV9zdGFnZZSMC1ZJREVPX1JFQURZlIwQc2NlbmVfZHJhZnRfcGF0aJSMAJSMDm1hcmtl"
    "cl9jYXRhbG9nlH2UKGgBjBJobWItbWFya2VyLWNhdGFsb2eUjAd2ZXJzaW9ulEsEjAljaGFyYWN0ZXKUXZQofZQojARuYW1llIwD"
    "UmVklIwEa2luZJSMBXNvbGlklIwDcmdilF2UKEc/8AAAAAAAAEcAAAAAAAAAAEcAAAAAAAAAAGV1fZQoaBaMBUdyZWVulGgYjAVz"
    "b2xpZJRoGl2UKEcAAAAAAAAAAEc/8AAAAAAAAEcAAAAAAAAAAGV1fZQoaBaMBEJsdWWUaBiMBXNvbGlklGgaXZQoRwAAAAAAAAAA"
    "RwAAAAAAAAAARz/wAAAAAAAAZXV9lChoFowGWWVsbG93lGgYjAVzb2xpZJRoGl2UKEc/8AAAAAAAAEc/7MzMzMzMzUcAAAAAAAAA"
    "AGV1fZQoaBaMBk9yYW5nZZRoGIwFc29saWSUaBpdlChHP/AAAAAAAABHP+Cj1wo9cKRHP8cKPXCj1wpldX2UKGgWjAZQdXJwbGWU"
    "aBiMBXNvbGlklGgaXZQoRz/iPXCj1wo9Rz/R64UeuFHsRz/wAAAAAAAAZXV9lChoFowEUGlua5RoGIwFc29saWSUaBpdlChHP+0e"
    "uFHrhR9HP9MzMzMzMzNHP+I9cKPXCj1ldWWMCmJhY2tncm91bmSUXZQofZQoaBaMCFNreSBCbHVllGgYjAVzb2xpZJRoGl2UKEc/"
    "1wo9cKPXCkc/5wo9cKPXCkc/8AAAAAAAAGV1fZQoaBaMBE1pbnSUaBiMBXNvbGlklGgaXZQoRz/ZmZmZmZmaRz/tcKPXCj1xRz/n"
    "XCj1wo9cZXV9lChoFowFQmVpZ2WUaBiMBXNvbGlklGgaXZQoRz/rhR64UeuFRz/o9cKPXCj2Rz/keuFHrhR7ZXV9lChoFowRRGly"
    "ZWN0aW9uIENoZWNrZXKUaBiMB3BhdHRlcm6UjAdwYXR0ZXJulIwRZGlyZWN0aW9uX2NoZWNrZXKUjBNzY3JlZW5fc3BhY2VfaWRf"
    "cmdilF2UKEv/SwBL/2V1fZQoaBaMCFNreSBHcmlklGgYjAdwYXR0ZXJulGhFjAhza3lfZ3JpZJRoR12UKEsAS/9L/2V1fZQoaBaM"
    "CkZsb29yIEdyaWSUaBiMB3BhdHRlcm6UaEWMCmZsb29yX2dyaWSUaEddlChL/0v/S/9ldX2UKGgWjBBQb3NpdGlvbiBQYXR0ZXJu"
    "lGgYjAdwYXR0ZXJulGhFjBBwb3NpdGlvbl9wYXR0ZXJulGhHXZQoSwBL/0t/ZXVljAdvcHRpb25zlF2UKGgXaB1oIWglaCloLWgx"
    "aDdoO2g/aENoSmhPaFRldYwWbWFya2VyX2NhdGFsb2dfdmVyc2lvbpRLBIwSc2NlbmVfcmVxdWVzdF9wYXRolGgOjARtb2RllIwE"
    "bWF5YZSMBnN0YXR1c5RoDIwHbWVzc2FnZZSMLEltcG9ydGVkIDEgTVA0IGZpbGUocykgaW50byB0aGUgY3V0IGhpc3RvcnkulIwK"
    "dmlkZW9fcGF0aJSMcEM6L1VzZXJzL2poX2Fobi9Eb2N1bWVudHMvR3JpcHRhcGVOb2Rlcy9pbnB1dHMvdGVzdF9kZWwvZTEwMXMw"
    "NTljMDAxX18vZTEwMXMwNTljMDAxX19fcGxheWJsYXN0X2ZlOWRmZGMxMmI0ZC5tcDSUjAl2aWRlb191cmyUjKVodHRwOi8vbG9j"
    "YWxob3N0OjgxMjQvZXh0ZXJuYWwvQzovVXNlcnMvamhfYWhuL0RvY3VtZW50cy9HcmlwdGFwZU5vZGVzL2lucHV0cy90ZXN0X2Rl"
    "bC9lMTAxczA1OWMwMDFfXy9lMTAxczA1OWMwMDFfX19wbGF5Ymxhc3RfZmU5ZGZkYzEyYjRkLm1wND92PTE3ODYyNDM4MjYxMjkz"
    "MjYzMDCUjBNvcmlnaW5hbF92aWRlb19wYXRolGgOjBJvcmlnaW5hbF92aWRlb191cmyUaA6MEW9yaWdpbmFsX21ldGFkYXRhlH2U"
    "jBBvcmlnaW5hbF9lbmFibGVklImMDG1hc2tfZW5hYmxlZJSIjBNtYXNrX2F1dGhvcmluZ19zbG90lEsBjBhvcmlnaW5hbF9wcmV2"
    "aWV3X2VuYWJsZWSUiYwNZGVwdGhfZW5hYmxlZJSJjBRtb3Rpb25fZ3VpZGVfZW5hYmxlZJSJjBBkZXB0aF92aWRlb19zbG90lEsA"
    "jBdtb3Rpb25fZ3VpZGVfdmlkZW9fc2xvdJRLAIwPc25hcHNob3RfYWN0aXZllImMDnNuYXBzaG90X2ZyYW1llEcAAAAAAAAAAIwT"
    "c25hcHNob3RfdmlkZW9fc2xvdJRLAIwRc25hcHNob3RfZGF0YV91cmmUaA6MDXNuYXBzaG90X3BhdGiUaA6MDHNuYXBzaG90X3Vy"
    "bJRoDowPc25hcHNob3Rfc2hhMjU2lGgOjBNhY3RpdmVfc25hcHNob3RfdWlklGgOjA12aWV3cG9ydF9tb2RllIwFdmlkZW+UjBpz"
    "bmFwc2hvdF9yZXF1ZXN0X3ZpZGVvX3VpZJRoDowJc25hcHNob3RzlF2UjApzY2VuZV9wYXRolGgOjBFuYXRpdmVfcmVhZF9yZWFk"
    "eZSJjBBuYXRpdmVfcmVhZF9tb2RllGgOjBVuYXRpdmVfc291cmNlX3ZlcnNpb26UaA6MD25hdGl2ZV9tZXRhZGF0YZR9lIwGY2Ft"
    "ZXJhlGgOjApzb3VyY2VfZnBzlEcAAAAAAAAAAIwKb3V0cHV0X2Zwc5RHAAAAAAAAAACMDG91dHB1dF93aWR0aJRNAAWMDW91dHB1"
    "dF9oZWlnaHSUTdACjBJzb3VyY2VfZnJhbWVfY291bnSUSwCMEm91dHB1dF9mcmFtZV9jb3VudJRLAIwTZGVjb2RlZF9mcmFtZV9j"
    "b3VudJRLAIwXc291cmNlX2R1cmF0aW9uX3NlY29uZHOURwAAAAAAAAAAjBdvdXRwdXRfZHVyYXRpb25fc2Vjb25kc5RHAAAAAAAA"
    "AACMDmZyYW1lX21ldGFkYXRhlH2UKIwKdmlkZW9fc2xvdJSMB0B2aWRlbzGUjANmcHOURwAAAAAAAAAAjAtzdGFydF9mcmFtZZRL"
    "AYwJZW5kX2ZyYW1llEsAjAtmcmFtZV9jb3VudJRLAGiLSwCMEG1heWFfc3RhcnRfZnJhbWWUTowObWF5YV9lbmRfZnJhbWWUTowQ"
    "ZHVyYXRpb25fc2Vjb25kc5RHAAAAAAAAAACMCHRpbWViYXNllGgOjAV3aWR0aJRLAIwGaGVpZ2h0lEsAjApyZXNvbHV0aW9ulH2U"
    "KGiaSwBom0sAdYwRZnJhbWVfaW5kZXhfc3RhcnSUTowPZnJhbWVfaW5kZXhfZW5klE6MFWF2YWlsYWJsZV9jb2xvcl9waWNrc5Rd"
    "lIwGb3JpZ2lulIwGbWFudWFslIwIY29uZmxpY3SUiYwFdmFsaWSUiYwId2FybmluZ3OUXZQojBtGcmFtZSBjb3VudCBpcyB1bmF2"
    "YWlsYWJsZS6UjBNGUFMgaXMgdW5hdmFpbGFibGUulIwjRGlzcGxheSBmcmFtZSByYW5nZSBpcyB1bmF2YWlsYWJsZS6UZXVok0cA"
    "AAAAAAAAAGiURwAAAAAAAAAAjA1jdXJyZW50X2ZyYW1llEcAAAAAAAAAAIwUaGFzX21heWFfZnJhbWVfcmFuZ2WUiYwHbWFya2Vy"
    "c5RdlGimXZSMDGFjdGl2aXR5X2xvZ5RdlCh9lCiMBHRpbWWUjAgwOToxNToxNpSMBWxldmVslIwESU5GT5RoX4xwUHl0aG9uIGNv"
    "cmUgbG9hZGVkOiBDOi9Vc2Vycy9qaF9haG4vRG9jdW1lbnRzL0dyaXB0YXBlTm9kZXMvbGlicmFyaWVzL0hNQl9HUF9Qcm9kdWN0"
    "aW9uL0hNQlZpZGVvUGlja2VyTGlicmFyeS5weZR1fZQoaLOMCDA5OjE1OjE2lGi1jAdTVUNDRVNTlGhfjFJNYXlhIDIwMjcgbWF5"
    "YWJhdGNoIGRldGVjdGVkOiBDOi9Qcm9ncmFtIEZpbGVzL0F1dG9kZXNrL01heWEyMDI3L2Jpbi9tYXlhYmF0Y2guZXhllHV9lCho"
    "s4wIMDk6MTU6MTaUaLWMB1NVQ0NFU1OUaF+MXFJ1bnRpbWUgbW9kZTogU2hhcmVkIC8gT3JjaGVzdHJhdG9yLiBJc29sYXRlZCBX"
    "b3JrZXIgbW9kZSBpcyBkaXNhYmxlZCBmb3IgSE1CX0dQX1Byb2R1Y3Rpb24ulHV9lChos4wIMDk6MTU6MTaUaLWMB1NVQ0NFU1OU"
    "aF+MZFByaW1hcnkgd2lkZ2V0IHN0YXRlIHRyYW5zcG9ydDogcGFyYW1ldGVyPUhNQl9QSUNLRVJfU1RBVEUsIHR5cGU9ZGljdCwg"
    "c2V0dGFibGU9dHJ1ZSwgcHJvcGVydHk9dHJ1ZS6UdX2UKGizjAgwOToxNToxNpRotYwHU1VDQ0VTU5RoX4yaQWN0aW9uIHRyYW5z"
    "cG9ydDogZXhlY3V0aW9uIGFuZCBsYW5ndWFnZSBjb21tYW5kcyB1c2UgdGhlIGluZGVwZW5kZW50IEhNQl9QSUNLRVJfQ09NTUFO"
    "RCBtaW5pbWFsIEpTT04gcGF0aDsgSE1CX1BJQ0tFUl9TVEFURSBjYXJyaWVzIGRhc2hib2FyZCBzdGF0ZSBvbmx5LpR1fZQoaLOM"
    "CDA5OjE1OjE2lGi1jARJTkZPlGhfjCNXYWl0aW5nIGZvciBhIE1heWEgLm1iIG9yIC5tYSBmaWxlLpR1fZQoaLOMCDA5OjE2OjA5"
    "lGi1jAdTVUNDRVNTlGhfjCxJbXBvcnRlZCAxIE1QNCBmaWxlKHMpIGludG8gdGhlIGN1dCBoaXN0b3J5LpR1ZYwRYWN0aXZpdHlf"
    "bG9nX3RleHSUWPcCAABbMDk6MTU6MTZdIElORk8gIFB5dGhvbiBjb3JlIGxvYWRlZDogQzovVXNlcnMvamhfYWhuL0RvY3VtZW50"
    "cy9HcmlwdGFwZU5vZGVzL2xpYnJhcmllcy9ITUJfR1BfUHJvZHVjdGlvbi9ITUJWaWRlb1BpY2tlckxpYnJhcnkucHkKWzA5OjE1"
    "OjE2XSBTVUNDRVNTICBNYXlhIDIwMjcgbWF5YWJhdGNoIGRldGVjdGVkOiBDOi9Qcm9ncmFtIEZpbGVzL0F1dG9kZXNrL01heWEy"
    "MDI3L2Jpbi9tYXlhYmF0Y2guZXhlClswOToxNToxNl0gU1VDQ0VTUyAgUnVudGltZSBtb2RlOiBTaGFyZWQgLyBPcmNoZXN0cmF0"
    "b3IuIElzb2xhdGVkIFdvcmtlciBtb2RlIGlzIGRpc2FibGVkIGZvciBITUJfR1BfUHJvZHVjdGlvbi4KWzA5OjE1OjE2XSBTVUND"
    "RVNTICBQcmltYXJ5IHdpZGdldCBzdGF0ZSB0cmFuc3BvcnQ6IHBhcmFtZXRlcj1ITUJfUElDS0VSX1NUQVRFLCB0eXBlPWRpY3Qs"
    "IHNldHRhYmxlPXRydWUsIHByb3BlcnR5PXRydWUuClswOToxNToxNl0gU1VDQ0VTUyAgQWN0aW9uIHRyYW5zcG9ydDogZXhlY3V0"
    "aW9uIGFuZCBsYW5ndWFnZSBjb21tYW5kcyB1c2UgdGhlIGluZGVwZW5kZW50IEhNQl9QSUNLRVJfQ09NTUFORCBtaW5pbWFsIEpT"
    "T04gcGF0aDsgSE1CX1BJQ0tFUl9TVEFURSBjYXJyaWVzIGRhc2hib2FyZCBzdGF0ZSBvbmx5LgpbMDk6MTU6MTZdIElORk8gIFdh"
    "aXRpbmcgZm9yIGEgTWF5YSAubWIgb3IgLm1hIGZpbGUuClswOToxNjowOV0gU1VDQ0VTUyAgSW1wb3J0ZWQgMSBNUDQgZmlsZShz"
    "KSBpbnRvIHRoZSBjdXQgaGlzdG9yeS6UjB1hY3Rpdml0eV9sb2dfdGV4dF91c2VyX2VkaXRlZJSJjBRhY3Rpdml0eV9sb2dfY2xl"
    "YXJlZJSJjA9tYXlhX2V4ZWN1dGFibGWUjDRDOi9Qcm9ncmFtIEZpbGVzL0F1dG9kZXNrL01heWEyMDI3L2Jpbi9tYXlhYmF0Y2gu"
    "ZXhllIwMbWF5YV92ZXJzaW9ulIwEMjAyN5SMDm1heWFfYXZhaWxhYmxllIiMEmFjdGl2ZV9wcm9jZXNzX3BpZJRLAIwTYWN0aXZl"
    "X3Byb2Nlc3Nfa2luZJRoDowNbGFzdF9sb2dfcGF0aJRoDowKbG9nX2ZvbGRlcpRoDowOb3BlcmF0aW9uX2tpbmSUaA6MFG9wZXJh"
    "dGlvbl92aWRlb19zbG90lEsAjBdvcGVyYXRpb25fc3RhcnRlZF9hdF9tc5RLAIwYb3BlcmF0aW9uX2ZpbmlzaGVkX2F0X21zlEsA"
    "jBZsYXN0X29wZXJhdGlvbl9zZWNvbmRzlEcAAAAAAAAAAIwGcnVuX2lklGgOjAxvcGVyYXRpb25faWSUaA6MFm9wZXJhdGlvbl9p"
    "bnB1dF9kaWdlc3SUaA6MG29wZXJhdGlvbl9zY2VuZV9maW5nZXJwcmludJRoDowVb3BlcmF0aW9uX2ludmFsaWRhdGVklImMHW9w"
    "ZXJhdGlvbl9pbnZhbGlkYXRpb25fcmVhc29ulGgOjBJweXRob25fY29yZV9sb2FkZWSUiIwQcHl0aG9uX2NvcmVfcGF0aJSMXEM6"
    "L1VzZXJzL2poX2Fobi9Eb2N1bWVudHMvR3JpcHRhcGVOb2Rlcy9saWJyYXJpZXMvSE1CX0dQX1Byb2R1Y3Rpb24vSE1CVmlkZW9Q"
    "aWNrZXJMaWJyYXJ5LnB5lIwTcnVudGltZV9pbnN0YW5jZV9pZJRoB4wQc2NlbmVfcmVxdWVzdF9pZJRoDowUc2NlbmVfcmVxdWVz"
    "dF9zb3VyY2WUaA6MFHNjZW5lX3JlcXVlc3Rfc3RhdHVzlIwESURMRZSME3NlbGVjdGVkX3ZpZGVvX3Nsb3SUSwGMEWFjdGl2ZV9z"
    "bG90X2NvdW50lEsBjBRzZWxlY3RlZF92aWRlb19jb3VudJRLAYwTbWF4X3NlbGVjdGVkX3ZpZGVvc5RLCowMc2VsZWN0aW9uX2lk"
    "lIxAOGQ2MzZmNGUyMWFkNTBlYTVjYjQzMTRhZTJkZjllODgwNjczNDQwY2ZiZjMyZWQ1NDU1YmZkOGJkNTdlNWZkNZSMEXByZXZp"
    "ZXdfdmlkZW9fdWlklIwmdmlkZW8tMGE2NGUyMGZkNjZmNGZhMWE0YjRlM2VkOThhNTNlMzOUjBJzZWxlY3RlZF92aWRlb191aWSU"
    "aPeME3NlbGVjdGVkX3ZpZGVvX3BhdGiUjEp7aW5wdXRzfS90ZXN0X2RlbC9lMTAxczA1OWMwMDFfXy9lMTAxczA1OWMwMDFfX19w"
    "bGF5Ymxhc3RfZmU5ZGZkYzEyYjRkLm1wNJSMFXZpZGVvX2xpYnJhcnlfdmVyc2lvbpRLAYwOcGVuZGluZ19hY3Rpb26UaA6MEXBl"
    "bmRpbmdfYWN0aW9uX2lklGgOjBViYWNrZW5kX2Fja19hY3Rpb25faWSUjClicm93c2VfdmlkZW9fYXNzZXQtMTc4NzI3MTM2NjM3"
    "OC1jMzFjNjMzYZSMEWxvd2VyX3BhbmVsX3JhdGlvlEc/1cKPXCj1w4wQbWFpbl9zcGxpdF9yYXRpb5RHP+R64UeuFHuMEXJpZ2h0"
    "X3NwbGl0X3JhdGlvlEc/2uFHrhR64YwKbm9kZV93aWR0aJRLAIwLbm9kZV9oZWlnaHSUSwCMFW91dGxpbmVyX3BhbmVsX2hlaWdo"
    "dJRLAIwVdmlld3BvcnRfcGFuZWxfaGVpZ2h0lEsAjBVyaWdodF9zZWN0aW9uX2hlaWdodHOUfZQojAhzZXR0aW5nc5RL2YwFY29s"
    "b3KUTXQCjANsb2eUS9B1jBF1aV9sYXlvdXRfdmVyc2lvbpRLBowIdWlfdGhlbWWUjAFQlIwOd29ya3NwYWNlX3ZpZXeUjAlwbGF5"
    "Ymxhc3SUjBZzZWxlY3RlZF9vdXRsaW5lcl9wYXRolGgOjBZzZWxlY3RlZF9vdXRsaW5lcl9uYW1llGgOjBZzZWxlY3RlZF9vdXRs"
    "aW5lcl91dWlklGgOjA5zZWxlY3RlZF9jb2xvcpRoDowOb3V0bGluZXJfbm9kZXOUXZSMEW91dGxpbmVyX2V4cGFuZGVklF2UjAdj"
    "YW1lcmFzlF2UjA9zZWxlY3RlZF9jYW1lcmGUaA6MCGxhbmd1YWdllIwCa2+UjA9vdXRsaW5lcl9zZWFyY2iUaA6MBnZpZGVvc5Rd"
    "lH2UKGhhaGKMEnByb2plY3RfdmlkZW9fcGF0aJRo+owOdmlkZW9fbWV0YWRhdGGUfZQoaJpNAAVom03QAowFY29kZWOUjARoMjY0"
    "lIwKZnJhbWVfcmF0ZZRHQDgAAAAAAACMCWZpbGVfc2l6ZZRK62xSAIwGZm9ybWF0lIwDbW92lIwLY29sb3Jfc3BhY2WUjAVidDcw"
    "OZRomEdAFyqqwQlKLHVoY2hkaH5oDmitXZSMD2dlbmVyYXRpb25fcm9sZZSMCGltcG9ydGVklIwKbWVkaWFfa2luZJSMFmltcG9y"
    "dGVkX21wNF9yZWZlcmVuY2WUjAp2aWRlb19yb2xllIwXdXNlcl9pbXBvcnRlZF9yZWZlcmVuY2WUjBBzb3VyY2VfdHlwZV9oaW50"
    "lIwbVXNlciBJbXBvcnRlZCBDdXQgUmVmZXJlbmNllIwRY29udHJvbF9yb2xlX2hpbnSUjB1Vc2VyIFNlbGVjdGVkIFZpZGVvIFJl"
    "ZmVyZW5jZZSMBWxhYmVslIwlZTEwMXMwNTljMDAxX19fcGxheWJsYXN0X2ZlOWRmZGMxMmI0ZJSMEmltcG9ydF9zb3VyY2VfcGF0"
    "aJSMcEM6L1VzZXJzL2poX2Fobi9Eb2N1bWVudHMvR3JpcHRhcGVOb2Rlcy9pbnB1dHMvdGVzdF9kZWwvZTEwMXMwNTljMDAxX18v"
    "ZTEwMXMwNTljMDAxX19fcGxheWJsYXN0X2ZlOWRmZGMxMmI0ZC5tcDSUjA5pbXBvcnRlZF9hdF9tc5SKBgjVrCGgAYwJdmlkZW9f"
    "dWlklGj3jApzb3VyY2VfdWlklGj3jBBwaWNrZXJfc2hvdF91dWlklIwkMDAwMDAwMDAtMDAwMC00MDAwLTgwMDAtMDAwMDAwMDAw"
    "MDAxlIwNY2F0YWxvZ19vcmRlcpRLAYwIc2VsZWN0ZWSUiIwPc2VsZWN0aW9uX29yZGVylEsBaJBLAWiEaA5ohUcAAAAAAAAAAGiG"
    "RwAAAAAAAAAAaIxHAAAAAAAAAABojUcAAAAAAAAAAGiHSwBoiEsAaIlLAGiKSwBoi0sAaJNHAAAAAAAAAABolEcAAAAAAAAAAGis"
    "iWiOfZQoaJCMB0B2aWRlbzGUaJJHAAAAAAAAAABok0sBaJRLAGiVSwBoi0sAaJZOaJdOaJhHAAAAAAAAAABomWgOaJpLAGibSwBo"
    "nH2UKGiaSwBom0sAdWieTmifTmigXZRoomijaKSJaKWJaKZdlChoqGipaKpldYwLdGltaW5nX2N1ZXOUXZR1YYwQc2xvdF9hc3Np"
    "Z25tZW50c5RdlH2UKGiQSwGMCGJpbmRpbmdzlF2UdWGMD3Nsb3RfdmlzaWJpbGl0eZRdlH2UKGiQSwGMDGhpZGRlbl9wYXRoc5Rd"
    "lHVhjBdzbG90X3JlY292ZXJ5X2ZhbGxiYWNrc5RdlIwcc2hvdF9wdWJsaXNoZXJfaW5zdGFuY2VfdXVpZJSMJDExN2UyYjMxLTYx"
    "MGQtNDFlOC1hZGVmLTI1NTQzNjJhYTJiNpSMDGNoYW5uZWxfdXVpZJSMJGYxODFkN2QwLWU0OTYtNDE0ZC04NDI5LTk4YzBlYTNh"
    "ZTczNZSMCXNob3RfdXVpZJSMJGY3MTI4ZDIzLWExZWEtNGUzNS1iYTdjLTY5ZDI3YzNkMGIwNZSMC3Nob3RfbnVtYmVylEsBjAlz"
    "aG90X25hbWWUjAZTaG90IDGUjA9zaG90X3NlbGVjdGlvbnOUXZR9lChqWwEAAIwkZjcxMjhkMjMtYTFlYS00ZTM1LWJhN2MtNjlk"
    "MjdjM2QwYjA1lIwGbnVtYmVylEsBjARuYW1llGpfAQAAjAhyZXZpc2lvbpRLEIwTc2VsZWN0ZWRfdmlkZW9fdWlkc5RdlGj3YXVh"
    "jC1hY2NlcHRlZF9zaG90X2NhdGFsb2dfcHVibGlzaGVyX2luc3RhbmNlX3V1aWSUjCQxMTdlMmIzMS02MTBkLTQxZTgtYWRlZi0y"
    "NTU0MzYyYWEyYjaUjCJhY2NlcHRlZF9zaG90X2NhdGFsb2dfY2hhbm5lbF91dWlklIwkZjE4MWQ3ZDAtZTQ5Ni00MTRkLTg0Mjkt"
    "OThjMGVhM2FlNzM1lIwgYWNjZXB0ZWRfc2hvdF9jYXRhbG9nX2dlbmVyYXRpb26USxiMJWFjY2VwdGVkX3Nob3RfY2F0YWxvZ19t"
    "ZXRhZGF0YV9zaGEyNTaUjEBmMzRlZjMwNzMxZDZmYTE5YzYzM2ZlZWYyOGQ3NjkzYWE1MTY3YzBjZTMwNDFkMDBiZjZmMGUwNzc1"
    "YzA1OWQ0lIwMcGlja2VyX3Nob3RzlF2UfZQojA53b3Jrc3BhY2VfdXVpZJRqQAEAAGpkAQAASwFqZQEAAGpfAQAAjAtjdXN0b21f"
    "bmFtZZSJamYBAABLAYwPYm91bmRfc2hvdF91dWlklIwkZjcxMjhkMjMtYTFlYS00ZTM1LWJhN2MtNjlkMjdjM2QwYjA1lIwQdmlk"
    "ZW9fYXNzZXRfdWlkc5RdlGj3YWpnAQAAXZRo92Fo9mj3aA1oDmirRwAAAAAAAAAAaHloemh4aA5o8EsBjBFhdXRob3JpbmdfY29u"
    "dGV4dJR9lChoEksBaAtoDGgNaA5oW2gOaH5oDmjsaA5o7WgOaO5o72h/iWiAaA5ogWgOaIJ9lGiEaA5qGwEAAGgOahkBAABdlGiF"
    "RwAAAAAAAAAAaIZHAAAAAAAAAABoh0dAlAAAAAAAAGiIR0CGgAAAAAAAaIlHAAAAAAAAAABoikcAAAAAAAAAAGiLRwAAAAAAAAAA"
    "aIxHAAAAAAAAAABojUcAAAAAAAAAAGiOfZQoaJBokWiSRwAAAAAAAAAAaJNLAWiUSwBolUsAaItLAGiWTmiXTmiYRwAAAAAAAAAA"
    "aJloDmiaSwBom0sAaJx9lChomksAaJtLAHVonk5on05ooF2UaKJoo2ikiWiliWimXZQoaKhoqWiqZXVok0cAAAAAAAAAAGiURwAA"
    "AAAAAAAAaKtHAAAAAAAAAABorIlqDwEAAGoQAQAAahEBAABoDmoSAQAAaA5qEwEAAGgOahQBAABoDmoVAQAAXZRqFwEAAF2Uah4B"
    "AABoDmpLAQAAXZR9lChokEsBak4BAABdlHVhalABAABdlH2UKGiQSwFqUwEAAF2UdWForV2UaGVoDmhmaA5oZ32UaGyJaF5oDGhf"
    "aGB1dWGMF2FjdGl2ZV9waWNrZXJfc2hvdF91dWlklGpAAQAAjCJwaWNrZXJfbGVnYWN5X21lbWJlcnNoaXBfZmFsbGJhY2tzlH2U"
    "dS4="
)


def durable_signature(state):
    normalized = picker._parse_state(copy.deepcopy(state))
    return {
        "videos": [
            {
                "video_uid": item.get("video_uid"),
                "source_uid": item.get("source_uid"),
                "picker_shot_uuid": item.get("picker_shot_uuid"),
                "catalog_order": item.get("catalog_order"),
                "label": item.get("label"),
                "video_path": item.get("video_path"),
                "project_video_path": item.get("project_video_path"),
                "import_source_path": item.get("import_source_path"),
            }
            for item in normalized.get("videos", [])
            if isinstance(item, dict)
        ],
        "picker_shots": [
            {
                "workspace_uuid": row.get("workspace_uuid"),
                "bound_shot_uuid": row.get("bound_shot_uuid"),
                "number": row.get("number"),
                "name": row.get("name"),
                "video_asset_uids": list(row.get("video_asset_uids") or []),
                "selected_video_uids": list(row.get("selected_video_uids") or []),
                "preview_video_uid": row.get("preview_video_uid"),
            }
            for row in normalized.get("picker_shots", [])
            if isinstance(row, dict)
        ],
    }


def routing_signature(state):
    normalized = picker._parse_state(copy.deepcopy(state))
    return {
        "shot_publisher_instance_uuid": normalized.get(
            "shot_publisher_instance_uuid"
        ),
        "channel_uuid": normalized.get("channel_uuid"),
        "shot_uuid": normalized.get("shot_uuid"),
        "shot_number": normalized.get("shot_number"),
        "shot_name": normalized.get("shot_name"),
        "shot_selections": [
            {
                "shot_uuid": row.get("shot_uuid"),
                "number": row.get("number"),
                "name": row.get("name"),
                "revision": row.get("revision"),
                "selected_video_uids": list(
                    row.get("selected_video_uids") or []
                ),
            }
            for row in normalized.get("shot_selections", [])
            if isinstance(row, dict)
        ],
    }


saved_state = pickle.loads(base64.b64decode(_REAL_SAVED_PICKLE_B64))
assert saved_state["schema"] == "maya-video-picker-state"
assert len(saved_state["videos"]) == 1
saved_video_uid = "video-0a64e20fd66f4fa1a4b4e3ed98a53e33"
assert saved_state["videos"][0]["video_uid"] == saved_video_uid
assert saved_state["picker_shots"][0]["video_asset_uids"] == [saved_video_uid]
assert saved_state["picker_shots"][0]["selected_video_uids"] == [saved_video_uid]
assert saved_state["picker_shots"][0]["preview_video_uid"] == saved_video_uid
expected = durable_signature(saved_state)
expected_routing = routing_signature(saved_state)

catalog_shots = [
    {
        "shot_uuid": row["shot_uuid"],
        "number": row["number"],
        "name": row["name"],
        "revision": row["revision"],
    }
    for row in saved_state["shot_selections"]
]
catalog = {
    "schema": "hmb-shot-routing-catalog",
    "version": 1,
    "publisher_instance_uuid": saved_state[
        "accepted_shot_catalog_publisher_instance_uuid"
    ],
    "channel_uuid": saved_state["accepted_shot_catalog_channel_uuid"],
    "generation": saved_state["accepted_shot_catalog_generation"],
    "shots": catalog_shots,
}
catalog["metadata_sha256"] = picker._sha256_canonical(
    {
        "channel_uuid": catalog["channel_uuid"],
        "generation": catalog["generation"],
        "shots": catalog_shots,
    }
)
assert catalog["metadata_sha256"] == saved_state[
    "accepted_shot_catalog_metadata_sha256"
]

original_request = picker._request_parameter_value
picker._request_parameter_value = lambda *_args, **_kwargs: True
try:
    serialized = copy.deepcopy(saved_state)
    for replay_index in range(12):
        node = picker.HMBVideoPickerLibrary(
            name=f"real_saved_picker_replay_{replay_index}"
        )
        node._schedule_post_hydration_shot_reconcile = lambda: False
        node._sync_outputs_from_state = lambda _state: None
        parameter = picker._get_parameter_obj(
            node,
            picker.WIDGET_STATE_PARAMETER,
        )

        # Reproduce NodeManager.on_set_parameter_value_request exactly:
        # it invokes before_value_set even for initial_setup, then asks the node
        # setter to skip that already-completed hook.
        candidate = node.before_value_set(
            parameter,
            copy.deepcopy(serialized),
        )
        assert durable_signature(candidate) == expected
        assert routing_signature(candidate) == expected_routing
        assert candidate["runtime_instance_id"] != node._hmb_runtime_instance_id
        node.set_parameter_value(
            picker.WIDGET_STATE_PARAMETER,
            candidate,
            initial_setup=True,
            skip_before_value_set=True,
        )
        assert durable_signature(node._picker_state()) == expected
        assert routing_signature(node._picker_state()) == expected_routing
        assert (
            node._picker_state()["runtime_instance_id"]
            == node._hmb_runtime_instance_id
        )

        for hook_name in ("after_deserialize", "after_load", "on_loaded"):
            getattr(node, hook_name)()
            assert durable_signature(node._picker_state()) == expected
            assert routing_signature(node._picker_state()) == expected_routing
            node._hmb_reconcile_shot_routing_commit(copy.deepcopy(catalog))
            assert durable_signature(node._picker_state()) == expected
            assert routing_signature(node._picker_state()) == expected_routing

        # An empty browser echo from the cold-mount constructor cannot replace
        # the Python-owned Loader catalog.
        empty_echo = picker._default_widget_state()
        empty_echo.update(
            {
                "runtime_instance_id": node._hmb_runtime_instance_id,
                "state_writer": "widget",
                "state_revision": node._picker_state()["state_revision"],
            }
        )
        node.set_parameter_value(
            picker.WIDGET_STATE_PARAMETER,
            empty_echo,
        )
        assert durable_signature(node._picker_state()) == expected
        assert routing_signature(node._picker_state()) == expected_routing

        # A normal (non-initial_setup) Python publication bearing the previous
        # process writer token is a retired worker and must remain rejected.
        node.set_parameter_value(
            picker.WIDGET_STATE_PARAMETER,
            copy.deepcopy(saved_state),
            skip_before_value_set=True,
        )
        assert durable_signature(node._picker_state()) == expected
        assert routing_signature(node._picker_state()) == expected_routing

        serialized = pickle.loads(
            pickle.dumps(
                copy.deepcopy(
                    node.parameter_values[picker.WIDGET_STATE_PARAMETER]
                    if hasattr(node, "parameter_values")
                    else node._picker_state()
                ),
                protocol=pickle.HIGHEST_PROTOCOL,
            )
        )
        assert durable_signature(serialized) == expected
        assert routing_signature(serialized) == expected_routing
finally:
    picker._request_parameter_value = original_request


print("HMB VideoPicker real saved-workflow replay regression: PASS")
