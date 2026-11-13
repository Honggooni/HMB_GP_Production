"""Saved production rig: dormant intermediate SG faces must stay untouched.

Replays the actual transform390 failure shape. Uses the established Maya SG
model, not a successful renderer stub. No Maya process or scene file is opened.
"""
from __future__ import annotations
import ast
import copy
import fnmatch
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
from typing import Any

ROOT=Path(__file__).resolve().parents[2]
WORKER=ROOT/'resources/maya/HMB_Maya_Background_Preview.py'
FIXTURES=ROOT/'resources/tests/HMB_VideoPicker_Original_Lambert_Override_Regression.py'
maya=types.ModuleType('maya');maya.cmds=types.ModuleType('maya.cmds')
sys.modules.update({'maya':maya,'maya.cmds':maya.cmds})
spec=importlib.util.spec_from_file_location('hmb_intermediate_membership_worker',WORKER)
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
tree=ast.parse(FIXTURES.read_text('utf-8'))
wanted={'FakeMaterialCmds','MidgrayCmds','EyeMidgrayCmds','add_surface'}
namespace=dict(types=types,copy=copy,fnmatch=fnmatch,Any=Any,
    BASE_SCOPE_SHAPES=['meshA','meshB','meshC','meshD','meshE'])
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef))
    and n.name in wanted],type_ignores=[]),str(FIXTURES),'exec'),namespace)
Eye=namespace['EyeMidgrayCmds'];add_surface=namespace['add_surface']
OWNER='|history_GRP|transform390'
SHAPE=OWNER+'|historyEyeShape'
MEMBER='transform390.f[0:71]'
checks=[]

def material_snapshot(fake):
    state=list(fake.snapshot())
    # ShadingEngine membership is a set; Maya does not preserve query order.
    state[1]={key:sorted(value) for key,value in state[1].items()}
    return tuple(state)

class MaskEye(Eye):
    def delete(self,node):
        if str(node).startswith('HMB_Mask_Authored_RemainderSG'):
            self.members.pop(node,None)
            return namespace['FakeMaterialCmds'].delete(self,node)
        return super().delete(node)

def fixture(folder,fixture_type=Eye,**kwargs):
    fake=fixture_type(folder,**kwargs)
    add_surface(fake,SHAPE)
    fake.alias_paths['transform390']=[OWNER]
    fake.values[OWNER+'.visibility']=False
    fake.values[SHAPE+'.intermediateObject']=True
    fake.members['sharedEyeBodySG'].append(MEMBER)
    return fake

def controller(fake):
    runner.cmds=fake
    return runner._OriginalLambertOverrideController({
        'apply_original_lambert_override':True,
        'original_material_override_profile':runner.ORIGINAL_MATERIAL_OVERRIDE_PROFILE,
        '_viewport_quality_scope_shapes':[fake.EYE_LEFT,fake.EYE_RIGHT,fake.BODY]})

with tempfile.TemporaryDirectory(prefix='hmb-inactive-membership-') as temp:
    folder=Path(temp)
    fake=fixture(folder)
    ctl=controller(fake)
    before=material_snapshot(fake)
    try:
        ctl._member_shape(MEMBER)
    except RuntimeError as error:
        assert 'transform does not identify one surface' in str(error)
    else:
        raise AssertionError('Fixture no longer reproduces native transform390 resolution failure')
    checks.append('native_failure_reproduced_without_relaxing_member_resolution')
    applied=ctl.apply()
    assert applied['preserved_inactive_intermediate_member_count']==1
    assert applied['preserved_inactive_intermediate_members']==[
        {'shading_group':'sharedEyeBodySG','member':MEMBER,'shape':SHAPE}]
    assert MEMBER in fake.members['sharedEyeBodySG']
    assert set(fake.members['sharedEyeBodySG'])==set(fake.EYE_MEMBERS+[MEMBER])
    assert all(MEMBER not in members for _target,members in fake.assignment_calls)
    assert ctl.finish()['restore_ok'] and material_snapshot(fake)==before
    checks.append('hidden_intermediate_membership_preserved_while_real_body_split_restores')

    # Mask's AIPickerM material pass shares the controller and must preserve
    # the same dormant member without any unnecessary shading assignment.
    fake=fixture(folder);runner.cmds=fake;before=material_snapshot(fake)
    ctl=runner._OriginalLambertOverrideController({
        '_viewport_quality_scope_shapes':[fake.EYE_RIGHT],
        '_mask_material_pass_shapes':[fake.EYE_RIGHT]},material_pass_only=True)
    applied=ctl.apply()
    assert applied['preserved_inactive_intermediate_member_count']==1
    assert not fake.assignment_calls and material_snapshot(fake)==before
    assert ctl.finish()['restore_ok'] and material_snapshot(fake)==before
    checks.append('mask_material_pass_preserves_inactive_membership_without_edits')

    # Production shot1 also has an unavailable Redshift eye material. This
    # path revisits SG members after applying the native compatibility shader;
    # the original fix covered planning alone and failed at this second pass.
    for material_pass_only in (False,True):
        fake=fixture(folder,fixture_type=MaskEye if material_pass_only else Eye)
        fake.node_types['EyeMat']='unknown'
        runner.cmds=fake;before=material_snapshot(fake)
        if material_pass_only:
            ctl=runner._OriginalLambertOverrideController({
                '_viewport_quality_scope_shapes':[fake.EYE_RIGHT],
                '_mask_material_pass_shapes':[fake.EYE_RIGHT]},material_pass_only=True)
        else:
            ctl=controller(fake)
        applied=ctl.apply()
        assert applied['eye_fallback_applied'] and applied['eye_fallback_verified']
        assert applied['preserved_inactive_intermediate_member_count']==1
        assert MEMBER in fake.members['sharedEyeBodySG']
        assert all(SHAPE not in item['affected_shapes'] for item in applied['eye_fallback_records'])
        assert all(MEMBER not in members for _target,members in fake.assignment_calls)
        assert ctl.finish()['restore_ok'] and material_snapshot(fake)==before
        checks.append(('mask' if material_pass_only else 'original')+'_unavailable_renderer_fallback_preserves_history_and_restores')

    # A later membership traversal cannot invent proof or trust stale flags.
    # Simulate an external change after planning, then require material rollback.
    for label,change in (
        ('lost_proof',lambda f,c:c.inactive_intermediate_members.clear()),
        ('visibility_changed',lambda f,c:f.values.__setitem__(OWNER+'.visibility',True)),
    ):
        fake=fixture(folder);fake.node_types['EyeMat']='unknown'
        ctl=controller(fake);before=material_snapshot(fake)
        create_shader=ctl._create_eye_fallback_shader
        def changed_shader(material,source):
            shader=create_shader(material,source)
            change(fake,ctl)
            return shader
        ctl._create_eye_fallback_shader=changed_shader
        try:ctl.apply()
        except RuntimeError as error:assert 'cannot be resolved exactly' in str(error)
        else:raise AssertionError('Fallback trusted invalid intermediate proof: '+label)
        fake.values[OWNER+'.visibility']=False
        assert material_snapshot(fake)==before and ctl.report['restore_ok']
        assert all(MEMBER not in members for _target,members in fake.assignment_calls)
        checks.append(label+'_during_fallback_fails_and_restores_materials')

    # Missing/ambiguous evidence never gains the history-only exception.
    for label,mutate in (
        ('visible_owner',lambda f:f.values.__setitem__(OWNER+'.visibility',True)),
        ('missing_visibility',lambda f:f.values.pop(OWNER+'.visibility')),
        ('no_surface',lambda f:f.node_types.pop(SHAPE)),
        ('two_history_surfaces',lambda f:(add_surface(f,OWNER+'|secondHistory'),f.values.__setitem__(OWNER+'|secondHistory.intermediateObject',True))),
        ('ambiguous_owner',lambda f:f.alias_paths.__setitem__('transform390',[OWNER,'|other|transform390'])),
        ('unsupported_component',lambda f:f.members.__setitem__('sharedEyeBodySG',f.EYE_MEMBERS+['transform390.vtx[0:71]'])),
        ('two_final_surfaces',lambda f:(f.values.__setitem__(SHAPE+'.intermediateObject',False),add_surface(f,OWNER+'|secondFinal'))),
    ):
        fake=fixture(folder);mutate(fake);ctl=controller(fake);before=material_snapshot(fake)
        try:ctl.apply()
        except RuntimeError as error:
            assert 'cannot be resolved exactly' in str(error) or 'unsupported component' in str(error),(label,str(error))
        else:raise AssertionError('Unproven/ambiguous member was accepted: '+label)
        assert material_snapshot(fake)==before,label
        assert not fake.assignment_calls and not ctl.created_nodes,label
        checks.append(label+'_fails_before_material_mutation')

    # A scope or pass contradiction must fail the proof even if the queried
    # Maya flags claim that the same history mesh is intermediate.
    for label,scope,passed in (
        ('scope_contains_history',[SHAPE],set()),
        ('scope_contains_descendant',[OWNER+'|nested|renderShape'],set()),
        ('material_pass_contains_history',[],{SHAPE}),
        ('material_pass_contains_descendant',[],{OWNER+'|nested|renderShape'}),
    ):
        fake=fixture(folder);ctl=controller(fake);ctl.scope_shapes=scope
        assert ctl._inactive_intermediate_member_shape(MEMBER,passed)=='',label
        checks.append(label+'_does_not_bypass_resolution')

    # The one exact live surface keeps the ordinary split/restore behavior.
    fake=fixture(folder);fake.values[SHAPE+'.intermediateObject']=False
    ctl=controller(fake);before=material_snapshot(fake);applied=ctl.apply()
    assert applied['preserved_inactive_intermediate_member_count']==0
    assert MEMBER not in fake.members['sharedEyeBodySG']
    assert ctl.finish()['restore_ok'] and material_snapshot(fake)==before
    checks.append('actual_final_surface_keeps_existing_split_and_restore')

    # A later forceElement failure rolls back all touched real body members,
    # while the dormant original SG member was never submitted to Maya.
    fake=fixture(folder,fail_split_after=1);ctl=controller(fake);before=material_snapshot(fake)
    try:ctl.apply()
    except RuntimeError as error:assert 'intentional partial body membership' in str(error)
    else:raise AssertionError('Partial split failure was hidden')
    assert material_snapshot(fake)==before
    assert all(MEMBER not in members for _target,members in fake.assignment_calls)
    checks.append('partial_assignment_failure_restores_without_touching_history')

print(json.dumps({'passed':True,'checks':len(checks),'cases':checks,'maya_processes':0,'provider_calls':0},indent=2))
