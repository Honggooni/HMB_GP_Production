"""Offline checks of real per-role Maya orchestration and standalone Depth validation."""
from __future__ import annotations
import ast
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import HMBVideoPickerLibrary as picker

# Reuse only the deterministic report factory; production validators are imported normally.
fixture_tree = ast.parse((ROOT / 'resources/tests/HMB_Depth_Companion_Regression.py').read_text(encoding='utf-8'))
factory = next(node for node in fixture_tree.body if isinstance(node, ast.FunctionDef) and node.name == 'shader_depth_range_report')
factory_scope = {'picker': picker}
exec(compile(ast.Module(body=[factory], type_ignores=[]), '<depth-report-fixture>', 'exec'), factory_scope)

class SelectedRoleArtifactRegression(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hmb-selected-role-')
        self.root = Path(self.temp.name)
        self.private = self.root / '.hmb_video_picker' / 'selected'
        self.private.mkdir(parents=True)
        self.scene = self.root / 'scene.ma'
        self.scene.write_text('// offline fixture')

    def tearDown(self):
        self.temp.cleanup()

    def depth(self, first=101., last=102.):
        frames = [first, last]
        reference = dict(camera='|shotCam', fps=24., start_frame=first, end_frame=last,
                         frame_count=2, resolution={'width':64,'height':36},
                         frame_map=[dict(sequence_index=i,maya_frame=f) for i,f in enumerate(frames)])
        report = factory_scope['shader_depth_range_report'](frames)
        sidecar = dict(reference, schema='hmb-maya-depth-playblast', schema_version=1,
                       profile=picker.DEPTH_PLAYBLAST_PROFILE, depth_range_report=report)
        result = dict(ok=True, depth_profile=picker.DEPTH_PLAYBLAST_PROFILE, depth_frame_count=2,
                      depth_range_report=copy.deepcopy(report), depth_frame_map=copy.deepcopy(reference['frame_map']))
        paths = []
        for index in range(2):
            path = self.private / f'depth.{index:06d}.png'
            Image.linear_gradient('L').resize((64,36)).save(path)
            paths.append(path)
        return dict(result=result, color_sidecar=reference, depth_sidecar=sidecar,
                    color_frame_paths=(), depth_frame_paths=paths, expected_frame_count=2,
                    expected_fps=24., expected_start_frame=first, expected_end_frame=last,
                    expected_width=64, expected_height=36)

    def test_depth_alone_retains_real_shader_range_and_pixel_validation(self):
        args=self.depth()
        result=picker._validate_depth_companion_inputs(**args, standalone=True)
        self.assertIsInstance(result,dict)
        self.assertFalse(list(self.private.glob('color*')))
        with self.assertRaises(RuntimeError):
            picker._validate_depth_companion_inputs(**args)

    def test_depth_alone_rejects_bad_camera_range_frame_and_chroma(self):
        for defect in ('camera','range','frame','chroma','missing'):
            with self.subTest(defect=defect):
                args=self.depth()
                if defect=='camera': args['depth_sidecar']['camera']='|wrong'
                if defect=='range': args['depth_sidecar']['depth_range_report']['far']=-1
                if defect=='frame': args['depth_sidecar']['frame_map'][1]['maya_frame']=1000
                if defect=='chroma': Image.new('RGB',(64,36),(255,0,0)).save(args['depth_frame_paths'][0])
                if defect=='missing': args['depth_frame_paths'][0].unlink()
                with self.assertRaises((RuntimeError,ValueError)):
                    picker._validate_depth_companion_inputs(**args,standalone=True)

    def test_selected_executor_never_launches_a_sibling_pass(self):
        for role in ('color','depth','motion_guide'):
            with self.subTest(role=role):
                calls=[]
                job={'scene_path':str(self.scene),'capture_pass':role,'generate_depth_playblast':True,'generate_motion_guide':True}
                for prefix in ('','depth_','motion_guide_'):
                    job[prefix+'frames_folder']=str(self.private/(prefix+'frames'))
                    job[prefix+'sidecar_path']=str(self.private/(prefix+'sidecar.json'))
                controller=mock.Mock()
                controller._hmb_cancel_requested=threading.Event()
                controller._picker_state.return_value={}
                def capture(**kwargs):
                    current=kwargs['job']; kind=current['capture_pass']; calls.append(kind)
                    stem='' if kind=='color' else kind+'_'
                    sidecar=Path(current[stem+'sidecar_path']);sidecar.write_text('{}')
                    result={'ok':True,'capture_pass':kind,'scene_path':str(self.scene),
                            'frames_folder':current[stem+'frames_folder'],'sidecar_path':str(sidecar)}
                    if stem:result.update({stem+'frames_folder':current[stem+'frames_folder'],stem+'sidecar_path':str(sidecar)})
                    Path(current['result_path']).write_text(json.dumps(result))
                    return 0
                controller._run_shared_maya_capture.side_effect=capture
                picker.HMBVideoPickerLibrary._execute_maya_capture_passes(controller,job=job,command=['offline'],
                    job_path=self.private/'job.json',result_path=self.private/'result.json',log_path=self.root/'capture.log',context=None)
                self.assertEqual(calls,[role])

    def mask_helper(self, *, first=101.,last=102.,bad=None,role='mask',role_slot=2):
        count=picker._maya_sequence_frame_count(first,last)
        folder=self.private/'mask';folder.mkdir(exist_ok=True)
        job=dict(camera='|shotCam',start_frame=first,end_frame=last,fps=24.,width=64,height=36,
                 output_name='mask',frames_folder=str(folder),sidecar_path=str(self.private/'mask.json'))
        if role != 'mask':
            job.update({role+'_output_name': job['output_name'], role+'_frames_folder': job['frames_folder'],
                        role+'_sidecar_path': job['sidecar_path'], role+'_video_slot': role_slot})
        self.raw_markers=[{'color':'Red','asset_id':'Actor','shading_profile':{'profile':'source-mask-marker'}}]
        sidecar=dict(camera='|shotCam',scene_path=str(self.scene),fps=24.,start_frame=first,end_frame=last,
                     frame_count=count,resolution={'width':64,'height':36},
                     schema='raw-runner-schema',schema_version=99,video_slot=9,
                     markers=copy.deepcopy(self.raw_markers),available_color_picks=['Red'],
                     assignment_mode='raw-assignment-must-remain',profile='raw-profile-must-remain',
                     frame_map=[dict(sequence_index=i,maya_frame=min(first+i,last)) for i in range(count)])
        for i in range(count): Image.new('RGB',(64,36),(255,0,0)).save(folder/f'mask.{i:06d}.png')
        if bad=='camera':sidecar['camera']='|bad'
        if bad=='nan':sidecar['start_frame']=float('nan')
        if bad=='frame':sidecar['frame_map'][-1]['maya_frame']=999
        if bad=='image':(folder/'mask.000000.png').write_bytes(b'corrupt')
        Path(job['sidecar_path']).write_text(json.dumps(sidecar))
        node=mock.Mock()
        node._execute_maya_capture_passes.return_value=dict(ok=True,frames_folder=str(folder),sidecar_path=job['sidecar_path'],fps=24.,frame_count=count)
        node._publish_validated_playblast_artifact=picker.HMBVideoPickerLibrary._publish_validated_playblast_artifact
        def encode(**kwargs):
            self.last_encode_command = picker._build_ffmpeg_encode_command(
                ffmpeg=kwargs['ffmpeg'], frame_pattern=kwargs['frame_pattern'],
                output_path=kwargs['staged_video_path'], source_fps=kwargs['source_fps'],
                frame_count=kwargs['frame_count'], width=kwargs['width'], height=kwargs['height'])
            kwargs['staged_video_path'].write_bytes(b'offline-encoded-mp4')
        node._encode_playblast_sequence.side_effect=encode
        with mock.patch.multiple(picker,
            _validate_full_smooth_confirmation=mock.Mock(),_validate_world_pattern_runner_confirmation=mock.Mock(),
            _validate_mask_material_pass_confirmation=mock.Mock(),
            _validate_depth_companion_inputs=mock.Mock(return_value={'validated':True}),
            _validate_motion_guide_inputs=mock.Mock(return_value={'validated':True}),
            _validate_encoded_playblast=lambda *a,**k:{'ok':True},
            _is_structurally_valid_mp4=lambda p:Path(p).is_file() and Path(p).read_bytes()==b'offline-encoded-mp4',
            _copy_video_to_griptape_project=lambda *a,**k:(None,''),_external_media_url=lambda p:Path(p).as_uri()):
            value=picker.HMBVideoPickerLibrary._maya_selected_role_artifact(node,role=role,job=job,command=['offline'],
                job_path=self.private/'job.json',result_path=self.private/'result.json',log_path=self.root/'log',
                ffmpeg=Path('offline'),scene_path=self.scene,output_folder=self.root,context=None)
        node._write_state.assert_not_called()
        node._sync_outputs_from_state.assert_not_called()
        return value

    def test_selected_helper_returns_one_immutable_asset_without_provisional_ui(self):
        value=self.mask_helper()
        self.assertEqual(value['generated_item']['generation_role'],'mask')
        self.assertTrue(Path(value['video']).is_file())
        self.assertTrue(Path(value['json']).is_file())

    def test_every_selected_role_publishes_the_actual_host_encoder_settings(self):
        for role in ('mask','depth','motion_guide'):
            with self.subTest(role=role):
                value=self.mask_helper(role=role)
                metadata=json.loads(Path(value['json']).read_text())['video_format']
                command=self.last_encode_command
                for field, flag in (('encoder','-c:v'),('pixel_format','-pix_fmt'),('profile','-profile:v'),
                                    ('level','-level:v'),('preset','-preset'),('crf','-crf'),
                                    ('color_range','-color_range'),('color_space','-colorspace'),
                                    ('color_transfer','-color_trc'),('color_primaries','-color_primaries'),
                                    ('frame_rate','-framerate'),('track_timescale','-video_track_timescale'),
                                    ('gop_frames','-g'),('fps_mode','-fps_mode')):
                    self.assertEqual(str(metadata[field]),command[command.index(flag)+1],(role,field))
                self.assertEqual(metadata['container'],'MPEG-4')
                self.assertEqual(metadata['codec'],'H.264')

    def test_auxiliary_sidecars_are_marker_free_and_mask_metadata_is_preserved(self):
        for role in ('mask','depth','motion_guide'):
            with self.subTest(role=role):
                value=self.mask_helper(role=role)
                metadata=json.loads(Path(value['json']).read_text())
                self.assertEqual(metadata['markers'],self.raw_markers if role=='mask' else [])
                self.assertEqual(metadata['available_color_picks'],['Red'] if role=='mask' else [])
                self.assertEqual(metadata['assignment_mode'],'raw-assignment-must-remain')
                self.assertEqual(metadata['profile'],'raw-profile-must-remain')
                if role=='mask':
                    self.assertEqual(metadata['schema'],'raw-runner-schema')
                    self.assertEqual(metadata['schema_version'],99)
                    self.assertEqual(metadata['video_slot'],9)

    def test_auxiliary_public_semantics_use_own_job_slot_and_fractional_timeline(self):
        for role in ('depth','motion_guide'):
            for slot in (2,3):
                with self.subTest(role=role,slot=slot):
                    value=self.mask_helper(role=role,role_slot=slot,first=101.25,last=102.75)
                    metadata=json.loads(Path(value['json']).read_text())
                    expected=(dict(schema='hmb-depth-playblast',schema_version=1,background_value=0.0,
                                   depth_semantics='camera_space_near_white_far_black',normalization_scope='fixed_full_shot')
                              if role=='depth' else
                              dict(schema='hmb-motion-guide',schema_version=picker.MOTION_GUIDE_SIDECAR_SCHEMA_VERSION,
                                   background_rgb=[0,0,0],appearance_authority='zero',motion_authority='derived_decoder_of_video1_only'))
                    for key,expected_value in expected.items():
                        self.assertEqual(metadata[key],expected_value,(role,key))
                    self.assertEqual(metadata['video_slot'],slot)
                    self.assertEqual(metadata['frame_count'],3)
                    self.assertEqual(metadata['frame_map'][-1]['maya_frame'],102.75)
                    self.assertEqual(value['generated_item']['output_frame_count'],3)
                    self.assertEqual(value['generated_item']['source_fps'],24.)

    def test_selected_helper_preserves_fractional_endpoint(self):
        value=self.mask_helper(first=101.25,last=102.75)
        self.assertEqual(json.loads(Path(value['json']).read_text())['frame_map'][-1]['maya_frame'],102.75)
        self.assertNotIn('frame_map',value['generated_item'])
        self.assertEqual(value['generated_item']['output_frame_count'],3)

    def test_selected_helper_rejects_timing_camera_and_corrupt_media_before_encode(self):
        for bad in ('camera','nan','frame','image'):
            with self.subTest(bad=bad), self.assertRaises((RuntimeError,ValueError)):
                self.mask_helper(bad=bad)

if __name__=='__main__':unittest.main()
