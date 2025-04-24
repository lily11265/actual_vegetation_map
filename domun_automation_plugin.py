# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox, QToolBar
from qgis.core import *
from qgis.utils import iface
from .domun_automation_dialog import DomunAutomationDialog
import os
import zipfile
import glob
import processing
import time
import traceback
import urllib.request
import tempfile
import shutil

class DomunAutomationPlugin:
    """QGIS 도면 자동화 플러그인 메인 클래스"""

    def __init__(self, iface):
        """생성자"""
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        
        # 리소스 디렉토리 설정
        self.resources_dir = os.path.join(self.plugin_dir, 'resources')
        self.index_path = os.path.join(self.resources_dir, 'TN_MAPINDX_5K25K.gpkg')
        self.data_path_25k = os.path.join(self.resources_dir, 'big_data_land_25000')
        
        # 디버그 모드 설정
        self.debug_mode = True
        
        # 액션을 저장할 변수
        self.actions = []
        self.menu = '&도면 자동화'
        
        # 툴바를 저장할 변수
        self.toolbar = self.iface.addToolBar('도면 자동화')
        self.toolbar.setObjectName('DomunAutomationToolbar')
        
        # 다이얼로그 초기화
        self.dlg = None
        
    def initGui(self):
        """GUI 초기화"""
        # 메인 실행 액션
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        action = QAction(
            QIcon(icon_path),
            '도면 자동화 실행',
            self.iface.mainWindow()
        )
        action.triggered.connect(self.show_dialog)
        action.setEnabled(True)
        action.setStatusTip('도면 자동화 처리를 실행합니다')
        self.toolbar.addAction(action)
        self.iface.addPluginToMenu(self.menu, action)
        self.actions.append(action)
        
    def show_dialog(self):
        """다이얼로그 표시"""
        if self.dlg is None:
            self.dlg = DomunAutomationDialog(self.iface.mainWindow())
            # 실행 요청 시그널 연결
            self.dlg.run_requested.connect(self.run_with_settings)
        
        # 다이얼로그를 표시하기 전에 레이어 목록 갱신
        self.dlg.refresh_layers()
        self.dlg.clear_status()
        self.dlg.show()

    def unload(self):
        """플러그인 언로드"""
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        del self.toolbar

    def run(self):
        """플러그인 실행"""
        try:
            self.load_and_process_data()
        except Exception as e:
            self.debug_print(f"플러그인 실행 중 오류: {str(e)}")
            QMessageBox.critical(None, "오류", f"플러그인 실행 중 오류 발생: {str(e)}")

    def run_with_settings(self, settings):
        """다이얼로그에서 받은 설정으로 실행"""
        try:
            # 디버그 모드 설정
            self.debug_mode = settings['debug']
            
            # 레이어 선택 확인
            selected_layer = settings['layer']
            if not selected_layer:
                self.dlg.append_status("오류: 레이어를 선택해주세요.")
                return
            
            # 상태 메시지 업데이트
            self.dlg.append_status(f"선택된 레이어: {selected_layer.name()}")
            self.dlg.append_status(f"Snakes 설정 - Threshold: {settings['threshold']}, Alpha: {settings['alpha']}, Beta: {settings['beta']}, Iterations: {settings['iterations']}")
            self.dlg.append_status("처리를 시작합니다...")
            
            # 실제 처리 함수 호출
            self.load_and_process_data(selected_layer, settings)
            
        except Exception as e:
            error_msg = f"플러그인 실행 중 오류: {str(e)}"
            self.debug_print(error_msg)
            self.dlg.append_status(error_msg)
            QMessageBox.critical(None, "오류", error_msg)
    
    def debug_print(self, message):
        """디버그 모드일 때만 메시지 출력"""
        if self.debug_mode:
            current_time = time.strftime("%H:%M:%S")
            debug_msg = f"[DEBUG {current_time}] {message}"
            print(debug_msg)
            QgsMessageLog.logMessage(message, 'MergeSmallPolygons', Qgis.Info)
            
            # 다이얼로그가 있는 경우 상태 메시지 추가
            if self.dlg:
                self.dlg.append_status(debug_msg)
            
            try:
                self.iface.messageBar().pushMessage("DEBUG", message, level=Qgis.Info, duration=2)
            except:
                pass

    # 디버그 모드 전환 함수
    def toggle_debug_mode(self):
        """디버그 모드 켜기/끄기 전환"""
        self.debug_mode = not self.debug_mode
        message = f"디버그 모드: {'켜짐' if self.debug_mode else '꺼짐'}"
        print(message)
        self.iface.messageBar().pushMessage("정보", message, level=Qgis.Info)
    
    def load_and_process_data(self, active_layer, settings):
        """SHP 파일 불러오기, 라인→폴리곤 변환, 클리핑, 25000 스케일 폴리곤 병합 및 일반화까지 모두 처리"""
        try:
            self.debug_print("함수 실행 시작")
            
            # 시작 시간 기록
            start_time = time.time()
            
            # 레이어 확인
            if not active_layer or not active_layer.isValid():
                self.iface.messageBar().pushMessage("오류", "활성화된 레이어가 없거나 유효하지 않습니다.", level=Qgis.Critical)
                return
            
            self.debug_print(f"활성화된 레이어: {active_layer.name()}")
            
            # 1. 인덱스 맵 로드 (플러그인 내부 리소스 사용)
            if not os.path.exists(self.index_path):
                self.iface.messageBar().pushMessage("오류", f"인덱스 파일이 존재하지 않습니다: {self.index_path}", level=Qgis.Critical)
                return
                
            index_layer = QgsVectorLayer(self.index_path, "인덱스", "ogr")
            if not index_layer.isValid():
                self.iface.messageBar().pushMessage("오류", "인덱스 파일을 불러올 수 없습니다.", level=Qgis.Critical)
                return
            
            self.debug_print("인덱스 맵 로드 완료")
            
            # 활성화 레이어와 인덱스 레이어 간 겹침 확인
            index_data = self.find_overlapping_indices(active_layer, index_layer)
            
            if not index_data['25000_id'] and not index_data['5000_ids']:
                self.iface.messageBar().pushMessage("정보", "활성화된 레이어와 겹치는 인덱스를 찾을 수 없습니다.", level=Qgis.Warning)
                return
            
            # 불러온 레이어 목록 저장
            loaded_layers = {'25000': [], '5000': []}
            
            # 2. 25000 스케일 데이터 로드 (플러그인 내부 리소스 사용)
            map_25k_id = index_data['25000_id']
            loaded_25k = False
            if map_25k_id:
                if not os.path.exists(self.data_path_25k):
                    self.iface.messageBar().pushMessage("오류", f"데이터 폴더가 존재하지 않습니다: {self.data_path_25k}", level=Qgis.Critical)
                else:
                    path_25k = self.find_and_extract_zip(map_25k_id, self.data_path_25k)
                    if not path_25k:
                        self.iface.messageBar().pushMessage("오류", f"{map_25k_id} 관련 25000 데이터를 찾을 수 없습니다.", level=Qgis.Warning)
                    else:
                        layer_25k = self.load_shp_file(path_25k)
                        if layer_25k:
                            loaded_layers['25000'].append(layer_25k)
                            loaded_25k = True
            
            # 3. 5000 스케일 데이터 로드 (모든 겹치는 맵 로드)
            loaded_count = 0
            for map_5k_id in index_data['5000_ids']:
                path_5k = self.find_and_extract_zip(map_5k_id, self.data_path_25k, scale_type='5000')
                if not path_5k:
                    self.iface.messageBar().pushMessage("오류", f"{map_5k_id} 관련 5000 데이터를 찾을 수 없습니다.", level=Qgis.Warning)
                else:
                    layer_5k = self.load_shp_file(path_5k)
                    if layer_5k:
                        loaded_layers['5000'].append(layer_5k)
                        loaded_count += 1
            
            self.debug_print(f"로드된 레이어 수: 25000 스케일 = {len(loaded_layers['25000'])}, 5000 스케일 = {len(loaded_layers['5000'])}")
            
            all_loaded_layers = loaded_layers['25000'] + loaded_layers['5000']
            if not all_loaded_layers:
                self.iface.messageBar().pushMessage("경고", "로드된 레이어가 없습니다. 클리핑을 수행할 수 없습니다.", level=Qgis.Warning)
                return
            
            # 4. 활성화된 레이어를 폴리곤으로 변환
            self.debug_print("활성화된 레이어를 폴리곤으로 변환 시작")
            if active_layer.geometryType() == QgsWkbTypes.LineGeometry:
                polygon_layer = self.line_to_polygon(active_layer)
            else:
                self.debug_print("활성화된 레이어가 이미 폴리곤입니다. 변환을 건너뜁니다.")
                polygon_layer = active_layer
            
            if polygon_layer:
                # 5. 불러온 레이어들을 폴리곤으로 클리핑 (gdal:clipvectorbypolygon 모듈 사용)
                self.debug_print("클리핑 작업 시작")
                clipped_layers = {'25000': [], '5000': []}
                
                # 25000 스케일 레이어 클리핑
                for layer in loaded_layers['25000']:
                    self.debug_print(f"25000 스케일 레이어 클리핑 시도: {layer.name()}")
                    clipped_layer = self.clip_layer_with_polygon(layer, polygon_layer)
                    if clipped_layer:
                        clipped_layers['25000'].append(clipped_layer)
                
                # 5000 스케일 레이어 클리핑
                for layer in loaded_layers['5000']:
                    self.debug_print(f"5000 스케일 레이어 클리핑 시도: {layer.name()}")
                    clipped_layer = self.clip_layer_with_polygon(layer, polygon_layer)
                    if clipped_layer:
                        clipped_layers['5000'].append(clipped_layer)
                
                self.debug_print(f"클리핑 작업 완료: 25000={len(clipped_layers['25000'])}개, 5000={len(clipped_layers['5000'])}개")
                
                # 6. 25000 스케일 레이어에만 작은 폴리곤 병합 적용
                merged_layers = []
                for layer in clipped_layers['25000']:
                    self.debug_print(f"25000 스케일 레이어 작은 폴리곤 병합 시작: {layer.name()}")
                    merged_layer = self.merge_small_polygons(layer)
                    if merged_layer:
                        merged_layers.append(merged_layer)
                
                # 7. 25000 스케일 레이어에만 v.generalize snakes 알고리즘 적용
                generalized_layers = []
                for layer in merged_layers:
                    self.debug_print(f"25000 스케일 레이어 snakes 알고리즘 적용 시작: {layer.name()}")
                    generalized_layer = self.apply_snakes_generalization(layer, settings)  # settings 전달
                    if generalized_layer:
                        generalized_layers.append(generalized_layer)
                
                # 8. 5000 스케일 레이어들을 하나로 병합 및 가장자리 폴리곤 처리
                if clipped_layers['5000']:
                    self.debug_print("5000 스케일 레이어 병합 시작")
                    merged_5k_layer = self.merge_adjacent_polygons(clipped_layers['5000'])
                    
                    if merged_5k_layer:
                        # 9. 5000 스케일 병합 레이어를 초기 도면 범위 안에서 반전
                        self.debug_print("5000 스케일 레이어 반전 시작")
                        inverted_5k_layer = self.invert_polygon(merged_5k_layer, polygon_layer)
                        
                        if inverted_5k_layer and generalized_layers:
                            # 10. 반전된 폴리곤을 mask로 사용해서 smoothing된 25000 레이어 클리핑
                            self.debug_print("smoothing된 25000 레이어 클리핑 시작")
                            clipped_25k_generalized = self.clip_layer_with_polygon(generalized_layers[0], inverted_5k_layer)
                            
                            # 클리핑 후 멀티폴리곤이 있다면 분리
                            if clipped_25k_generalized:
                                self.debug_print("클리핑된 레이어의 멀티폴리곤 확인 및 분리")
                                clipped_25k_generalized = self.explode_multipolygons(clipped_25k_generalized)
        
                            if clipped_25k_generalized:
                                # 11. 최종적으로 5000 스케일 병합 레이어와 클리핑된 25000 레이어 병합
                                self.debug_print("최종 레이어 병합 시작")
                                final_layer = self.merge_final_layers(merged_5k_layer, clipped_25k_generalized)
                                
                                if final_layer:
                                    # 12. FRTP_NM과 L2_NAME 조건에 따른 피처 병합 추가
                                    self.debug_print("속성 조건에 따른 피처 병합 시작")
                                    final_layer = self.merge_features_by_attribute_condition(final_layer)

                                    # 13. fixgeometries로 구조 수정
                                    self.debug_print("13. fixgeometries로 구조 수정 시작")
                                    params_fix = {
                                        'INPUT': final_layer,
                                        'METHOD': 1,  # Structure method
                                        'OUTPUT': 'TEMPORARY_OUTPUT'
                                    }
                                    result_fix = processing.run("native:fixgeometries", params_fix)
                                    fixed_final_layer = result_fix['OUTPUT']

                                    if isinstance(fixed_final_layer, str):
                                        fixed_final_layer = QgsVectorLayer(fixed_final_layer, "fixed_final_layer", "ogr")
                                    fixed_final_layer.setName("fixed_final_result")
                                    QgsProject.instance().addMapLayer(fixed_final_layer)

                                    # 14. 폴리곤을 라인으로 변환
                                    self.debug_print("14. 폴리곤을 라인으로 변환 시작")
                                    params_polygons_to_lines = {
                                        'INPUT': fixed_final_layer,
                                        'OUTPUT': 'TEMPORARY_OUTPUT'
                                    }
                                    result_lines = processing.run("native:polygonstolines", params_polygons_to_lines)
                                    final_lines_layer = result_lines['OUTPUT']

                                    if isinstance(final_lines_layer, str):
                                        final_lines_layer = QgsVectorLayer(final_lines_layer, "final_lines", "ogr")
                                    final_lines_layer.setName("final_result_lines")
                                    QgsProject.instance().addMapLayer(final_lines_layer)

                                    # 15. 최종 결과물을 제외한 나머지 레이어와 압축을 푼 파일 삭제
                                    self.debug_print("15. 임시 파일 및 레이어 정리 시작")

                                    # 최종 결과 레이어 ID 저장
                                    final_layer_ids = [fixed_final_layer.id(), final_lines_layer.id()]

                                    # 프로젝트의 모든 레이어 확인
                                    all_layers = QgsProject.instance().mapLayers().values()
                                    for layer in all_layers:
                                        if layer.id() not in final_layer_ids:
                                            self.debug_print(f"레이어 제거: {layer.name()}")
                                            QgsProject.instance().removeMapLayer(layer.id())

                                    # 임시 폴더 및 압축 해제된 파일 삭제
                                    temp_dirs_to_delete = []

                                    # 5000스케일 도면이 다운로드된 임시 폴더 찾기
                                    for tmpdir in glob.glob(os.path.join(tempfile.gettempdir(), '*')):
                                        if os.path.isdir(tmpdir) and any(f.endswith('.shp') for f in os.listdir(tmpdir)):
                                            temp_dirs_to_delete.append(tmpdir)

                                    # 압축 해제된 폴더 삭제
                                    for dir_path in temp_dirs_to_delete:
                                        try:
                                            shutil.rmtree(dir_path)
                                            self.debug_print(f"임시 폴더 삭제: {dir_path}")
                                        except Exception as e:
                                            self.debug_print(f"폴더 삭제 실패: {dir_path} - {str(e)}")

                                    # 종료 시간 기록 및 총 소요 시간 출력
                                    end_time = time.time()
                                    elapsed_time = end_time - start_time
                                    self.debug_print(f"총 소요 시간: {elapsed_time:.2f}초")

                                    self.iface.messageBar().pushMessage("성공", 
                                        f"전체 처리 완료. 최종 레이어 생성: {final_lines_layer.name()}. " + 
                                        f"총 소요 시간: {elapsed_time:.2f}초", 
                                        level=Qgis.Success)
                                    return
                
                # 5000 스케일 레이어가 없거나 이후 처리에 실패한 경우
                # 종료 시간 기록 및 총 소요 시간 출력
                end_time = time.time()
                elapsed_time = end_time - start_time
                self.debug_print(f"총 소요 시간: {elapsed_time:.2f}초")
                
                self.iface.messageBar().pushMessage("성공", 
                    f"25000 스케일 맵 {len(generalized_layers)}개, 5000 스케일 맵 {len(clipped_layers['5000'])}개 처리 완료. " + 
                    f"25000 스케일 맵에 작은 폴리곤 병합 및 snakes 알고리즘 적용됨.", 
                    level=Qgis.Success)
            else:
                self.iface.messageBar().pushMessage("오류", "폴리곤 레이어를 생성하는데 실패했습니다.", level=Qgis.Critical)
        
        except Exception as e:
            # 자세한 오류 정보 출력
            error_msg = str(e)
            stack_trace = traceback.format_exc()
            self.debug_print(f"오류 발생: {error_msg}")
            self.debug_print(f"스택 트레이스: {stack_trace}")
            self.iface.messageBar().pushMessage("심각한 오류", f"처리 중 예외 발생: {error_msg}", level=Qgis.Critical)
            print(stack_trace)  # 콘솔에 스택 트레이스 출력
        
    # 여기에 원본 코드의 모든 함수를 메서드로 변환
    # (원본 코드의 모든 함수들을 self를 첫 번째 매개변수로 받는 메서드로 변경)
    
    def find_overlapping_indices(self, active_layer, index_layer):
        """활성화된 레이어와 인덱스 레이어 간 겹침 확인"""
        try:
            self.debug_print("인덱스 겹침 확인 시작")
            
            # 활성화 레이어의 범위 가져오기
            active_extent = active_layer.extent()
            active_geom = QgsGeometry.fromRect(active_extent)
            
            # 활성화 레이어의 CRS 확인 및 필요시 변환
            active_crs = active_layer.crs()
            index_crs = index_layer.crs()
            
            if active_crs != index_crs:
                self.debug_print(f"CRS 변환 필요: {active_crs.authid()} -> {index_crs.authid()}")
                transform = QgsCoordinateTransform(active_crs, index_crs, QgsProject.instance())
                active_geom.transform(transform)
            
            # 결과 저장용 변수 초기화
            max_area_25k = 0
            best_25k_id = None
            map_5k_ids = set()  # 중복 방지를 위해 set 사용
            
            # 인덱스 레이어에서 겹치는 피쳐 찾기
            feature_count = 0
            for feature in index_layer.getFeatures():
                feature_count += 1
                if active_geom.intersects(feature.geometry()):
                    intersection = active_geom.intersection(feature.geometry())
                    area = intersection.area()
                    
                    # 25000 스케일의 경우 가장 큰 겹침 영역 저장
                    if '25000_MAPIDCD_NO' in feature.fields().names() and feature['25000_MAPIDCD_NO']:
                        if area > max_area_25k:
                            max_area_25k = area
                            best_25k_id = feature['25000_MAPIDCD_NO']
                    
                    # 5000 스케일의 경우 모든 겹치는 ID 저장
                    if '5000_MAPIDCD_NO' in feature.fields().names() and feature['5000_MAPIDCD_NO']:
                        map_5k_ids.add(feature['5000_MAPIDCD_NO'])
            
            self.debug_print(f"검사한 인덱스 피쳐 수: {feature_count}")
            self.debug_print(f"25000 스케일 인덱스: {best_25k_id}")
            self.debug_print(f"5000 스케일 인덱스 수: {len(map_5k_ids)}")
            
            # 찾은 인덱스 ID 출력
            if best_25k_id:
                self.iface.messageBar().pushMessage("정보", f"25000 스케일 인덱스: {best_25k_id}", level=Qgis.Info)
            
            if map_5k_ids:
                ids_str = ', '.join(map(str, list(map_5k_ids)[:5]))
                if len(map_5k_ids) > 5:
                    ids_str += f" 외 {len(map_5k_ids) - 5}개"
                self.iface.messageBar().pushMessage("정보", f"5000 스케일 인덱스: {ids_str}", level=Qgis.Info)
            
            return {
                '25000_id': best_25k_id,
                '5000_ids': list(map_5k_ids)
            }
        except Exception as e:
            self.debug_print(f"인덱스 겹침 확인 중 오류: {str(e)}")
            print(traceback.format_exc())
            return {'25000_id': None, '5000_ids': []}

    def find_and_extract_zip(self, map_id, folder_path, scale_type='25000'):
        """맵 ID와 폴더 경로로 ZIP 파일 찾아서 압축 해제 또는 다운로드"""
        try:
            self.debug_print(f"ZIP 파일 찾기/다운로드 시작: {map_id}, 스케일: {scale_type}")
            
            if scale_type == '5000':
                # 5000 스케일 도면은 URL에서 다운로드
                url = f"https://map.forest.go.kr/fgisfile/fgisData/DATA003/doyeop/{map_id}.zip"
                self.debug_print(f"5000스케일 도면 다운로드 URL: {url}")
                
                # 임시 폴더에 다운로드
                temp_dir = tempfile.mkdtemp()
                zip_file = os.path.join(temp_dir, f"{map_id}.zip")
                
                try:
                    urllib.request.urlretrieve(url, zip_file)
                    self.debug_print(f"다운로드 완료: {zip_file}")
                except Exception as e:
                    self.debug_print(f"다운로드 실패: {str(e)}")
                    shutil.rmtree(temp_dir)
                    return None
                
                extract_folder = os.path.join(temp_dir, map_id)
            else:
                # 기존 로직 (25000 스케일)
                zip_pattern = os.path.join(folder_path, f"*{map_id}*.zip")
                zip_files = glob.glob(zip_pattern)
                
                if not zip_files:
                    self.debug_print(f"ZIP 파일 찾기 실패: {map_id}")
                    return None
                
                zip_file = zip_files[0]
                extract_folder = zip_file.replace('.zip', '')
            
            # 압축 해제
            self.debug_print(f"압축 해제 중: {zip_file}")
            os.makedirs(extract_folder, exist_ok=True)
            
            try:
                with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                    zip_ref.extractall(extract_folder)
                self.debug_print(f"압축 해제 완료: {extract_folder}")
            except Exception as e:
                self.debug_print(f"압축 해제 실패: {str(e)}")
                if scale_type == '5000':
                    shutil.rmtree(temp_dir)
                return None
            
            # SHP 파일 찾기
            shp_files = glob.glob(os.path.join(extract_folder, "*.shp"))
            if not shp_files:
                self.debug_print(f"SHP 파일 찾기 실패: {extract_folder}")
                if scale_type == '5000':
                    shutil.rmtree(temp_dir)
                return None
            
            self.debug_print(f"찾은 SHP 파일: {os.path.basename(shp_files[0])}")
            return shp_files[0]
            
        except Exception as e:
            self.debug_print(f"ZIP 파일 처리 중 오류: {str(e)}")
            print(traceback.format_exc())
            return None

    def load_shp_file(self, shp_path):
        """SHP 파일 경로로 레이어 로드"""
        try:
            self.debug_print(f"SHP 파일 로드 시작: {os.path.basename(shp_path)}")
            
            layer_name = os.path.basename(shp_path).split('.')[0]
            layer = QgsVectorLayer(shp_path, layer_name, "ogr")
            
            if not layer.isValid():
                self.debug_print(f"SHP 파일 로드 실패: {os.path.basename(shp_path)}")
                self.iface.messageBar().pushMessage("오류", f"SHP 파일을 불러올 수 없습니다: {shp_path}", level=Qgis.Critical)
                return None
            
            # 레이어를 맵에 추가
            QgsProject.instance().addMapLayer(layer)
            self.debug_print(f"SHP 파일 로드 완료: {layer_name}, 피쳐 수: {layer.featureCount()}")
            self.iface.messageBar().pushMessage("정보", f"{layer_name} 레이어가 로드되었습니다.", level=Qgis.Info)
            return layer
        except Exception as e:
            self.debug_print(f"SHP 파일 로드 중 오류: {str(e)}")
            print(traceback.format_exc())
            return None

    def line_to_polygon(self, line_layer):
        """라인 레이어를 폴리곤으로 변환 (native:linestopolygons 사용)"""
        try:
            self.debug_print("라인을 폴리곤으로 변환 함수 시작")
            
            # 레이어의 이름 가져오기
            layer_name = line_layer.name()
            
            # 라인을 폴리곤으로 변환
            self.debug_print("라인을 폴리곤으로 변환 알고리즘 실행")
            
            result = processing.run("qgis:linestopolygons", {
                'INPUT': line_layer,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            })
            
            # 결과 처리
            if isinstance(result['OUTPUT'], str):
                self.debug_print("결과가 문자열 경로로 반환됨")
                polygon_layer = QgsVectorLayer(result['OUTPUT'], f"{layer_name}_polygon", "ogr")
            else:
                self.debug_print("결과가 레이어 객체로 반환됨")
                polygon_layer = result['OUTPUT']
                polygon_layer.setName(f"{layer_name}_polygon")
            
            # 도형 수정 (fixgeometries) 적용
            self.debug_print("폴리곤 도형 수정 시작")
            fixed_result = processing.run("qgis:linestopolygons", {
                'INPUT': polygon_layer,
                'METHOD': 1,  # Structure
                'OUTPUT': 'TEMPORARY_OUTPUT'
            })
            
            # 수정된 결과 처리
            if isinstance(fixed_result['OUTPUT'], str):
                fixed_polygon_layer = QgsVectorLayer(fixed_result['OUTPUT'], f"{layer_name}_polygon_fixed", "ogr")
            else:
                fixed_polygon_layer = fixed_result['OUTPUT']
                fixed_polygon_layer.setName(f"{layer_name}_polygon_fixed")
            
            # 프로젝트에 추가
            QgsProject.instance().addMapLayer(fixed_polygon_layer)
            
            if fixed_polygon_layer.featureCount() == 0:
                self.debug_print("변환된 폴리곤 레이어에 피쳐가 없습니다.")
                self.iface.messageBar().pushMessage("경고", "변환된 폴리곤 레이어에 피쳐가 없습니다.", level=Qgis.Warning)
                return None
            
            self.debug_print(f"폴리곤 변환 및 도형 수정 완료. 피쳐 수: {fixed_polygon_layer.featureCount()}")
            return fixed_polygon_layer
        
        except Exception as e:
            self.debug_print(f"라인을 폴리곤으로 변환 중 오류 발생: {str(e)}")
            print(traceback.format_exc())
            self.iface.messageBar().pushMessage("오류", f"라인을 폴리곤으로 변환 중 오류 발생: {str(e)}", level=Qgis.Critical)
            return None

    def clip_layer_with_polygon(self, input_layer, mask_layer):
        """레이어를 폴리곤으로 클리핑 (native:clip 사용)"""
        try:
            self.debug_print(f"레이어 클리핑 시작: {input_layer.name()}")
            
            # 레이어의 이름 가져오기
            layer_name = input_layer.name()
            
            # 입력 레이어 도형 수정
            self.debug_print(f"입력 레이어 도형 수정: {layer_name}")
            fixed_input_result = processing.run("native:fixgeometries", {
                'INPUT': input_layer,
                'METHOD': 1,  # Structure 
                'OUTPUT': 'TEMPORARY_OUTPUT'
            })
            
            if isinstance(fixed_input_result['OUTPUT'], str):
                fixed_input_layer = QgsVectorLayer(fixed_input_result['OUTPUT'], f"{layer_name}_fixed", "ogr")
            else:
                fixed_input_layer = fixed_input_result['OUTPUT']
            
            # 마스크 레이어 도형 수정
            self.debug_print(f"마스크 레이어 도형 수정: {mask_layer.name()}")
            fixed_mask_result = processing.run("native:fixgeometries", {
                'INPUT': mask_layer,
                'METHOD': 1,  # Structure
                'OUTPUT': 'TEMPORARY_OUTPUT'
            })
            
            if isinstance(fixed_mask_result['OUTPUT'], str):
                fixed_mask_layer = QgsVectorLayer(fixed_mask_result['OUTPUT'], f"{mask_layer.name()}_fixed", "ogr")
            else:
                fixed_mask_layer = fixed_mask_result['OUTPUT']
            
            # 수정된 레이어로 클리핑 실행
            self.debug_print(f"{layer_name} 레이어 클리핑 알고리즘 실행")
            result = processing.run("native:clip", {
                'INPUT': fixed_input_layer,
                'OVERLAY': fixed_mask_layer,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            })
            
            # 결과 처리
            clipped_layer = result['OUTPUT']
            
            # 결과가 문자열(경로)인 경우 레이어 객체로 변환
            if isinstance(clipped_layer, str):
                self.debug_print("결과가 문자열 경로로 반환됨")
                clipped_layer = QgsVectorLayer(clipped_layer, f"{layer_name}_clipped", "ogr")
                
                if not clipped_layer.isValid():
                    self.debug_print(f"클리핑된 레이어 로드 실패: {layer_name}")
                    return None
            else:
                clipped_layer.setName(f"{layer_name}_clipped")
            
            # 클리핑된 레이어도 도형 수정
            self.debug_print(f"클리핑된 레이어 도형 수정")
            fixed_clipped_result = processing.run("native:fixgeometries", {
                'INPUT': clipped_layer,
                'METHOD': 1,  # Structure
                'OUTPUT': 'TEMPORARY_OUTPUT'
            })
            
            if isinstance(fixed_clipped_result['OUTPUT'], str):
                final_layer = QgsVectorLayer(fixed_clipped_result['OUTPUT'], f"{layer_name}_clipped", "ogr")
            else:
                final_layer = fixed_clipped_result['OUTPUT']
                final_layer.setName(f"{layer_name}_clipped")
            
            # 원본 레이어가 아직 존재하는지 확인하고 제거
            try:
                if QgsProject.instance().mapLayer(input_layer.id()):
                    QgsProject.instance().removeMapLayer(input_layer.id())
                    self.debug_print(f"원본 레이어 {layer_name} 제거 완료")
            except RuntimeError:
                self.debug_print(f"원본 레이어 {layer_name} 제거 중 오류 - 이미 삭제됨")
            
            # 최종 레이어를 프로젝트에 추가
            if final_layer.isValid():
                QgsProject.instance().addMapLayer(final_layer)
                feature_count = final_layer.featureCount()
                
                if feature_count <= 0:
                    self.debug_print(f"클리핑 결과 피처가 없습니다: {layer_name}")
                    self.iface.messageBar().pushMessage("경고", f"{layer_name}: 클리핑 후 피처가 없습니다.", level=Qgis.Warning)
                else:
                    self.debug_print(f"클리핑 완료: {final_layer.name()}, 피처 수: {feature_count}")
                
                return final_layer
            else:
                self.debug_print(f"클리핑된 레이어가 유효하지 않음: {layer_name}")
                return None
        
        except Exception as e:
            self.debug_print(f"레이어 클리핑 중 오류 발생: {str(e)}")
            print(traceback.format_exc())
            self.iface.messageBar().pushMessage("오류", f"레이어 클리핑 중 오류 발생: {str(e)}", level=Qgis.Critical)
            return None

    def clean_with_grass(self, layer):
        """GRASS v.clean을 사용하여 폴리곤 정리"""
        try:
            self.debug_print(f"========== GRASS v.clean 실행 시작: {layer.name()} ==========")
            self.debug_print(f"입력 레이어 피처 수: {layer.featureCount()}")
            
            # GRASS v.clean 파라미터 설정 - rmarea 제거
            params = {
                'input': layer,
                'type': [3],  # 3은 area (polygon)
                'tool': [0, 1, 6],  # break, snap, rmdangle 도구만 사용 (rmarea 제거)
                'threshold': [0, 0.0001, 0.0001],  # 각 도구별 임계값
                '-c': False,  # 결합된 도구를 사용하지 않음
                'output': 'TEMPORARY_OUTPUT',
                'error': 'TEMPORARY_OUTPUT',
                'GRASS_REGION_PARAMETER': None,
                'GRASS_SNAP_TOLERANCE_PARAMETER': -1,
                'GRASS_MIN_AREA_PARAMETER': 0.0001,
                'GRASS_OUTPUT_TYPE_PARAMETER': 0,
                'GRASS_VECTOR_DSCO': '',
                'GRASS_VECTOR_LCO': ''
            }
            
            # v.clean 실행
            result = processing.run("grass7:v.clean", params)
            
            # 결과 레이어 가져오기
            cleaned_layer_path = result['output']
            self.debug_print(f"GRASS v.clean 출력 경로: {cleaned_layer_path}")
            
            # 문자열 경로를 QgsVectorLayer 객체로 변환
            if isinstance(cleaned_layer_path, str):
                cleaned_layer = QgsVectorLayer(cleaned_layer_path, "cleaned_layer", "ogr")
                if not cleaned_layer.isValid():
                    self.debug_print(f"GRASS v.clean 결과 레이어 로드 실패: {cleaned_layer_path}")
                    return None
                self.debug_print(f"GRASS v.clean 후 피처 수: {cleaned_layer.featureCount()}")
            else:
                cleaned_layer = cleaned_layer_path
                self.debug_print(f"GRASS v.clean 후 피처 수: {cleaned_layer.featureCount()}")
            
            # 피처가 없는 경우 원본 레이어 반환
            if cleaned_layer.featureCount() == 0:
                self.debug_print("GRASS v.clean 후 피처가 없음. 원본 레이어 반환")
                return layer
            
            self.debug_print(f"GRASS v.clean 완료")
            return cleaned_layer
            
        except Exception as e:
            self.debug_print(f"GRASS v.clean 실행 중 오류: {str(e)}")
            self.iface.messageBar().pushMessage("오류", f"GRASS v.clean 실행 중 오류: {str(e)}", level=Qgis.Critical)
            return None
        
    def merge_small_polygons(self,layer, area_threshold=125):
        """작은 폴리곤을 인접한 큰 폴리곤과 병합 - 수정된 버전"""
        try:
            self.debug_print(f"========== 작은 폴리곤 병합 시작: {layer.name()} ==========")
            self.debug_print(f"임계값: {area_threshold}")
            self.debug_print(f"입력 레이어 피처 수: {layer.featureCount()}")
            
            # 먼저 GRASS v.clean 실행하여 기본적인 토폴로지 문제 해결
            cleaned_layer = self.clean_with_grass(layer)
            if cleaned_layer and cleaned_layer.featureCount() > 0:
                # cleaned_layer가 문자열 경로인 경우 QgsVectorLayer로 변환
                if isinstance(cleaned_layer, str):
                    work_layer = QgsVectorLayer(cleaned_layer, "cleaned_layer", "ogr")
                    if not work_layer.isValid():
                        self.debug_print("정리된 레이어 로드 실패, 원본 레이어 사용")
                        work_layer = layer
                    else:
                        self.debug_print(f"GRASS v.clean 후 정리된 레이어 사용. 피처 수: {work_layer.featureCount()}")
                else:
                    work_layer = cleaned_layer
            else:
                self.debug_print("GRASS v.clean 실패 또는 피처 없음, 원본 레이어 사용")
                work_layer = layer
            
            # 레이어가 없거나 폴리곤이 아닌 경우 처리 중단
            if not work_layer or work_layer.geometryType() != QgsWkbTypes.PolygonGeometry:
                self.debug_print("폴리곤 레이어가 아니므로 병합 불가")
                self.iface.messageBar().pushMessage("오류", "폴리곤 레이어가 필요합니다.", level=Qgis.Critical)
                return layer
            
            # 시작 피처 수 기록
            initial_feature_count = work_layer.featureCount()
            self.debug_print(f"작업 시작 시 피처 수: {initial_feature_count}")
            
            # 피처가 없는 경우 원본 레이어 반환
            if initial_feature_count == 0:
                self.debug_print("작업할 피처가 없습니다. 원본 레이어 반환")
                return layer
            
            # 편집 모드 시작
            if not work_layer.startEditing():
                self.debug_print("편집 모드 시작 실패")
                self.iface.messageBar().pushMessage("오류", "레이어 편집 모드를 시작할 수 없습니다.", level=Qgis.Critical)
                return False
            
            # "면적" 필드가 없으면 추가
            area_field_index = work_layer.fields().indexFromName("면적")
            if area_field_index == -1:
                area_field = QgsField("면적", QVariant.Double)
                work_layer.addAttribute(area_field)
                area_field_index = work_layer.fields().indexFromName("면적")
            
            # 모든 피처에 대해 면적 계산
            for feature in work_layer.getFeatures():
                area = feature.geometry().area()
                work_layer.changeAttributeValue(feature.id(), area_field_index, area)
            
            # 면적 계산 저장
            if not work_layer.commitChanges():
                self.debug_print("면적 계산 저장 실패")
                return False
            
            # 편집 모드 다시 시작
            if not work_layer.startEditing():
                return False
            
            # 모든 피처 데이터 저장
            all_features = {}
            small_features = []
            large_features = []
            
            for feature in work_layer.getFeatures():
                fid = feature.id()
                area = feature["면적"]
                
                # 지오메트리 복사본 생성
                all_features[fid] = {
                    'feature': QgsFeature(feature),
                    'area': area,
                    'geometry': QgsGeometry(feature.geometry()),
                    'original_geom': QgsGeometry(feature.geometry())  # 원본 지오메트리 백업
                }
                
                if area <= area_threshold:
                    small_features.append(fid)
                else:
                    large_features.append(fid)
            
            self.debug_print(f"작은 피처 수: {len(small_features)}, 큰 피처 수: {len(large_features)}")
            
            if not small_features:
                self.debug_print("병합할 작은 피처가 없습니다.")
                work_layer.rollBack()
                return True
            
            # 공간 인덱스 생성 (큰 피처만)
            index = QgsSpatialIndex()
            for fid in large_features:
                index.addFeature(all_features[fid]['feature'])
            
            deleted_features = set()
            updated_features = set()
            
            # 각 작은 피처를 개별적으로 처리
            for small_fid in small_features:
                if small_fid in deleted_features:  # 이미 삭제된 피처는 건너뜀
                    continue
                    
                small_geom = all_features[small_fid]['geometry']
                
                # 인접한 큰 피처 찾기
                candidates = index.intersects(small_geom.boundingBox())
                best_target = None
                max_shared_length = 0
                
                for candidate_id in candidates:
                    if candidate_id in small_features:  # 작은 피처는 대상에서 제외
                        continue
                        
                    candidate_geom = all_features[candidate_id]['geometry']
                    
                    # 접촉 여부 확인
                    if small_geom.touches(candidate_geom):
                        try:
                            # 공유 경계선 길이 계산
                            shared_boundary = small_geom.intersection(candidate_geom)
                            shared_length = shared_boundary.length()
                            
                            if shared_length > max_shared_length:
                                max_shared_length = shared_length
                                best_target = candidate_id
                        except:
                            continue
                
                # 병합 대상을 찾은 경우
                if best_target is not None:
                    try:
                        target_feature = all_features[best_target]['feature']
                        target_geom = QgsGeometry(all_features[best_target]['geometry'])
                        
                        # 기존 면적 저장
                        original_target_area = target_geom.area()
                        
                        # union을 사용한 병합
                        merged_geom = target_geom.combine(small_geom)
                        
                        # 더 철저한 지오메트리 유효성 검사 및 수정
                        if not merged_geom.isGeosValid():
                            self.debug_print(f"피처 {small_fid} 병합 결과 무효한 지오메트리 발생")
                            merged_geom = merged_geom.makeValid()
                            
                            # 여전히 유효하지 않다면 buffer(0) 기법 사용
                            if not merged_geom.isGeosValid():
                                self.debug_print(f"피처 {small_fid} makeValid 실패, buffer(0) 시도")
                                merged_geom = merged_geom.buffer(0, 5)
                                
                            # 마지막으로 단순화 시도
                            if not merged_geom.isGeosValid():
                                self.debug_print(f"피처 {small_fid} buffer(0) 실패, simplify 시도")
                                merged_geom = merged_geom.simplify(0.00001)
                        
                        # 지오메트리 타입 확인
                        if merged_geom.wkbType() != QgsWkbTypes.Polygon:
                            if merged_geom.wkbType() == QgsWkbTypes.MultiPolygon:
                                self.debug_print(f"피처 {small_fid} 병합 결과 MultiPolygon 생성")
                                parts = merged_geom.asMultiPolygon()
                                if len(parts) == 1:
                                    merged_geom = QgsGeometry.fromPolygonXY(parts[0])
                                    self.debug_print(f"피처 {small_fid} MultiPolygon을 Polygon으로 변환")
                        
                        # 면적 검증
                        new_area = merged_geom.area()
                        expected_area = original_target_area + small_geom.area()
                        
                        # 토폴로지 오류 검사
                        errors = merged_geom.validateGeometry()
                        if errors:
                            self.debug_print(f"피처 {small_fid} 병합 후 토폴로지 오류: {errors}")
                        
                        # 면적이 크게 변하지 않았고 유효한 경우에만 병합
                        if (merged_geom.isGeosValid() and 
                            new_area > 0 and 
                            abs(new_area - expected_area) < expected_area * 0.1):  # 10% 오차 허용
                            
                            # 타겟 피처 업데이트
                            target_feature.setGeometry(merged_geom)
                            work_layer.updateFeature(target_feature)
                            work_layer.changeAttributeValue(best_target, area_field_index, new_area)
                            
                            # 작은 피처 삭제
                            work_layer.deleteFeature(small_fid)
                            
                            deleted_features.add(small_fid)
                            updated_features.add(best_target)
                            
                            # 메모리에 저장된 지오메트리도 업데이트
                            all_features[best_target]['geometry'] = merged_geom
                            
                            self.debug_print(f"피처 {small_fid}를 {best_target}에 병합 성공")
                        else:
                            self.debug_print(f"피처 {small_fid} 병합 실패: 지오메트리 검증 실패")
                            self.debug_print(f"유효성: {merged_geom.isGeosValid()}, 면적: {new_area}, 예상 면적: {expected_area}")
                        
                    except Exception as e:
                        self.debug_print(f"피처 {small_fid} 병합 중 오류: {str(e)}")
                        continue
            
            # 최종 저장
            if work_layer.commitChanges():
                final_feature_count = work_layer.featureCount()
                self.debug_print(f"병합 완료: {len(deleted_features)}개 삭제")
                self.debug_print(f"최종 피처 수: {final_feature_count}")
                
                # 피처 수 확인
                if final_feature_count != initial_feature_count - len(deleted_features):
                    self.debug_print(f"경고: 예상치 못한 피처 수 변경! 예상: {initial_feature_count - len(deleted_features)}, 실제: {final_feature_count}")
                
                # 레이어 갱신
                work_layer.updateExtents()
                work_layer.triggerRepaint()
                iface.mapCanvas().refresh()
                
                # 결과를 원본 레이어에 적용
                if cleaned_layer and work_layer != layer:
                    # 원본 레이어의 이름을 미리 저장
                    original_layer_name = layer.name()
                    
                    # 원본 레이어 제거
                    QgsProject.instance().removeMapLayer(layer.id())
                    
                    # 새 레이어에 원본 레이어의 이름 설정
                    work_layer.setName(original_layer_name)
                    
                    # 새 레이어를 프로젝트에 추가
                    QgsProject.instance().addMapLayer(work_layer)
                    
                    self.debug_print(f"원본 레이어 '{original_layer_name}'을 정리된 레이어로 교체 완료")
                
                iface.messageBar().pushMessage("성공", f"{len(deleted_features)}개의 작은 피처가 병합되었습니다.", level=Qgis.Success)
                return work_layer  # 최종적으로 사용된 레이어 반환
            else:
                self.debug_print("병합 작업 저장 실패")
                work_layer.rollBack()
                return layer  # 실패 시 원본 레이어 반환
        
        except Exception as e:
            self.debug_print(f"작은 폴리곤 병합 중 오류 발생: {str(e)}")
            import traceback
            self.debug_print(f"상세 오류: {traceback.format_exc()}")
            
            if 'work_layer' in locals() and work_layer.isEditable():
                work_layer.rollBack()
            
            self.iface.messageBar().pushMessage("오류", f"작은 폴리곤 병합 중 오류 발생: {str(e)}", level=Qgis.Critical)
            return layer  # 오류 발생 시 원본 레이어 반환


    def apply_snakes_generalization(self, layer, settings):
        """25000 스케일 레이어에 GRASS v.generalize의 snakes 알고리즘 적용"""
        try:
            self.debug_print(f"========== Snakes 알고리즘 일반화 시작: {layer.name()} ==========")
            
            # 설정값 사용
            threshold = settings.get('threshold', 1.0)
            alpha = settings.get('alpha', 1.0)
            beta = settings.get('beta', 1.0)
            iterations = settings.get('iterations', 1)
            
            # GRASS v.generalize 파라미터 설정
            params = {
                'input': layer,
                'type': [0, 1, 2],  # 0=point, 1=line, 2=boundary
                'method': 10,  # 10=snakes 알고리즘
                'threshold': threshold,  # 사용자 설정값 사용
                '-l': True,  # 경계선 처리
                '-t': False,  # 태그 처리
                'alpha': alpha,  # 사용자 설정값 사용
                'beta': beta,  # 사용자 설정값 사용
                'iterations': iterations,  # 사용자 설정값 사용
                'look_ahead': 7,
                'reduction': 50,
                'slide': 0.5,
                'angle_thresh': 3,
                'betweeness_thresh': 0,
                'closeness_thresh': 0,
                'degree_thresh': 0,
                'cats': '',
                'where': '',
                'output': 'TEMPORARY_OUTPUT',
                'error': 'TEMPORARY_OUTPUT',
                'GRASS_REGION_PARAMETER': None,
                'GRASS_SNAP_TOLERANCE_PARAMETER': -1,
                'GRASS_MIN_AREA_PARAMETER': 0.0001,
                'GRASS_OUTPUT_TYPE_PARAMETER': 0,
                'GRASS_VECTOR_DSCO': '',
                'GRASS_VECTOR_LCO': '',
                'GRASS_VECTOR_EXPORT_NOCAT': False
            }
            
            # 원본 레이어의 이름 저장
            original_layer_name = layer.name()
            
            # v.generalize 실행
            self.debug_print(f"{layer.name()} 레이어에 snakes 알고리즘 적용 시작")
            result = processing.run("grass7:v.generalize", params)
            
            # 결과 레이어 가져오기
            generalized_layer_path = result['output']
            
            # 문자열 경로를 QgsVectorLayer 객체로 변환
            if isinstance(generalized_layer_path, str):
                generalized_layer = QgsVectorLayer(generalized_layer_path, f"{original_layer_name}_generalized", "ogr")
                if not generalized_layer.isValid():
                    self.debug_print(f"GRASS v.generalize 결과 레이어 로드 실패: {generalized_layer_path}")
                    return None
            else:
                generalized_layer = generalized_layer_path
                generalized_layer.setName(f"{original_layer_name}_generalized")
            
            # 원본 레이어가 아직 존재하는지 확인하고 제거
            try:
                if QgsProject.instance().mapLayer(layer.id()):
                    QgsProject.instance().removeMapLayer(layer.id())
                    self.debug_print(f"원본 레이어 {original_layer_name} 제거 완료")
                else:
                    self.debug_print(f"원본 레이어 {original_layer_name}가 이미 제거됨")
            except RuntimeError:
                self.debug_print(f"원본 레이어 {original_layer_name} 제거 중 오류 - 이미 삭제됨")
            
            # 일반화된 레이어를 프로젝트에 추가
            QgsProject.instance().addMapLayer(generalized_layer)
            
            self.debug_print(f"Snakes 알고리즘 일반화 완료: {generalized_layer.name()}")
            self.iface.messageBar().pushMessage("성공", f"{original_layer_name} 레이어에 snakes 알고리즘 적용 완료", level=Qgis.Success)
            return generalized_layer
            
        except Exception as e:
            self.debug_print(f"Snakes 알고리즘 일반화 중 오류: {str(e)}")
            print(traceback.format_exc())
            self.iface.messageBar().pushMessage("오류", f"Snakes 알고리즘 일반화 중 오류: {str(e)}", level=Qgis.Critical)
            return None

    def merge_adjacent_polygons(self, layers):
        """여러 개의 5000 스케일 레이어를 하나로 병합하고 가장자리 폴리곤들만 병합"""
        try:
            self.debug_print(f"========== 5000 스케일 레이어 병합 시작 ==========")
            self.debug_print(f"병합할 레이어 수: {len(layers)}")
            
            if not layers:
                self.debug_print("병합할 레이어가 없습니다.")
                return None
            
            # 모든 레이어가 유효한지 확인
            valid_layers = []
            for layer in layers:
                if layer.isValid() and layer.featureCount() > 0:
                    valid_layers.append(layer)
                else:
                    self.debug_print(f"유효하지 않은 레이어 건너뜀: {layer.name()}")
            
            if not valid_layers:
                self.debug_print("유효한 레이어가 없습니다.")
                return None
            
            # 모든 레이어를 하나로 병합 (속성 유지)
            self.debug_print("모든 5000 스케일 레이어 병합 중...")
            params_merge = {
                'LAYERS': valid_layers,
                'CRS': valid_layers[0].crs(),
                'OUTPUT': 'TEMPORARY_OUTPUT'
            }
            
            result_merge = processing.run("native:mergevectorlayers", params_merge)
            merged_layer = result_merge['OUTPUT']
            
            if isinstance(merged_layer, str):
                merged_layer = QgsVectorLayer(merged_layer, "merged_5k", "ogr")
                if not merged_layer.isValid():
                    self.debug_print("병합된 레이어가 유효하지 않음")
                    return None
            
            merged_layer.setName("merged_5k")
            
            # GRASS v.clean 실행
            self.debug_print("GRASS v.clean 실행 중...")
            cleaned_layer = self.clean_with_grass(merged_layer)
            
            if cleaned_layer:
                if isinstance(cleaned_layer, str):
                    work_layer = QgsVectorLayer(cleaned_layer, "cleaned_merged_5k", "ogr")
                else:
                    work_layer = cleaned_layer
            else:
                work_layer = merged_layer
            
            # 경계선에 있는 폴리곤만 선택하여 병합
            self.debug_print("가장자리 폴리곤 병합 중...")
            
            # 편집 모드 시작
            if not work_layer.startEditing():
                self.debug_print("편집 모드 시작 실패")
                return work_layer
            
            # 각 레이어의 범위를 저장
            layer_extents = {}
            for i, layer in enumerate(layers):
                layer_extents[i] = layer.extent()
                self.debug_print(f"레이어 {i} 범위: {layer_extents[i].toString()}")
            
            # 공간 인덱스 생성
            spatial_index = QgsSpatialIndex()
            features_dict = {}
            
            for feat in work_layer.getFeatures():
                features_dict[feat.id()] = feat
                spatial_index.addFeature(feat)
            
            # 병합할 피처들 찾기
            to_merge = []
            processed = set()
            
            for fid, feature in features_dict.items():
                if fid in processed:
                    continue
                
                # 현재 피처가 어느 원본 레이어의 가장자리에 있는지 확인
                is_edge = False
                feature_geom = feature.geometry()
                
                # 각 원본 레이어의 경계선과 교차하는지 확인
                for extent in layer_extents.values():
                    extent_geom = QgsGeometry.fromRect(extent)
                    if feature_geom.intersects(extent_geom) and feature_geom.touches(extent_geom):
                        is_edge = True
                        break
                
                if not is_edge:
                    continue
                
                # 이 피처와 접하는 다른 피처들 찾기
                candidates = spatial_index.intersects(feature_geom.boundingBox())
                merge_group = [fid]
                
                for candidate_id in candidates:
                    if candidate_id == fid or candidate_id in processed:
                        continue
                    
                    candidate_feature = features_dict[candidate_id]
                    candidate_geom = candidate_feature.geometry()
                    
                    # 다른 레이어의 가장자리에 있는지 확인
                    is_candidate_edge = False
                    for extent in layer_extents.values():
                        extent_geom = QgsGeometry.fromRect(extent)
                        if candidate_geom.intersects(extent_geom) and candidate_geom.touches(extent_geom):
                            is_candidate_edge = True
                            break
                    
                    # 접하고 있는지 확인
                    if is_candidate_edge and feature_geom.touches(candidate_geom):
                        merge_group.append(candidate_id)
                
                if len(merge_group) > 1:
                    to_merge.append(merge_group)
                    processed.update(merge_group)
            
            # 병합 실행
            for group in to_merge:
                if len(group) < 2:
                    continue
                
                # 그룹의 첫 번째 피처를 기준으로 병합
                base_feature_id = group[0]
                base_feature = features_dict[base_feature_id]
                base_geom = base_feature.geometry()
                
                for other_id in group[1:]:
                    other_feature = features_dict[other_id]
                    other_geom = other_feature.geometry()
                    
                    # 지오메트리 병합
                    merged_geom = base_geom.combine(other_geom)
                    
                    # 유효성 검사
                    if not merged_geom.isGeosValid():
                        merged_geom = merged_geom.makeValid()
                    
                    if merged_geom.isGeosValid():
                        base_geom = merged_geom
                        # 병합된 피처 삭제
                        work_layer.deleteFeature(other_id)
                
                # 기준 피처 업데이트
                base_feature.setGeometry(base_geom)
                work_layer.updateFeature(base_feature)
            
            # 변경사항 저장
            if work_layer.commitChanges():
                self.debug_print(f"가장자리 폴리곤 병합 완료: {len(to_merge)}개 그룹 병합")
                work_layer.setName("merged_5k_final")
                QgsProject.instance().addMapLayer(work_layer)
                return work_layer
            else:
                self.debug_print("병합 작업 저장 실패")
                work_layer.rollBack()
                return None
            
        except Exception as e:
            self.debug_print(f"5000 스케일 레이어 병합 중 오류: {str(e)}")
            print(traceback.format_exc())
            if 'work_layer' in locals() and work_layer.isEditable():
                work_layer.rollBack()
            self.iface.messageBar().pushMessage("오류", f"5000 스케일 레이어 병합 중 오류: {str(e)}", level=Qgis.Critical)
            return None

    def merge_final_layers(self, layer_5k, layer_25k):
        """5000 스케일 레이어와 smoothing된 25000 스케일 레이어를 최종 병합"""
        try:
            self.debug_print(f"========== 최종 레이어 병합 시작 ==========")
            
            # 레이어 유효성 검사
            if not layer_5k.isValid() or not layer_25k.isValid():
                self.debug_print("입력 레이어가 유효하지 않습니다.")
                return None
            
            # 지오메트리 타입 확인
            if layer_5k.geometryType() != layer_25k.geometryType():
                self.debug_print(f"지오메트리 타입 불일치: {layer_5k.geometryType()} vs {layer_25k.geometryType()}")
                return None
            
            # 각 레이어의 초기 피처 수 확인
            initial_5k_count = layer_5k.featureCount()
            initial_25k_count = layer_25k.featureCount()
            self.debug_print(f"초기 피처 수 - 5k: {initial_5k_count}, 25k: {initial_25k_count}")
            
            # 먼저 모든 지오메트리가 유효한지 확인하고 수정
            self.debug_print("지오메트리 유효성 검사 및 수정 중...")
            
            # 5k 레이어 검사 및 수정 - METHOD를 0으로 변경 (현재 구조 유지)
            params_fix_5k = {
                'INPUT': layer_5k,
                'METHOD': 0,  # Keep current structure - 구조 변경 없이 유지
                'OUTPUT': 'TEMPORARY_OUTPUT'
            }
            
            result_fix_5k = processing.run("native:fixgeometries", params_fix_5k)
            fixed_5k = result_fix_5k['OUTPUT']
            
            # 25k 레이어 검사 및 수정 - METHOD를 0으로 변경 (현재 구조 유지)
            params_fix_25k = {
                'INPUT': layer_25k,
                'METHOD': 0,  # Keep current structure - 구조 변경 없이 유지
                'OUTPUT': 'TEMPORARY_OUTPUT'
            }
            
            result_fix_25k = processing.run("native:fixgeometries", params_fix_25k)
            fixed_25k = result_fix_25k['OUTPUT']
            
            # 수정 후 피처 수 확인
            fixed_5k_count = fixed_5k.featureCount()
            fixed_25k_count = fixed_25k.featureCount()
            self.debug_print(f"수정 후 피처 수 - 5k: {fixed_5k_count}, 25k: {fixed_25k_count}")
            
            if fixed_25k_count < initial_25k_count:
                self.debug_print(f"경고: 25k 레이어에서 {initial_25k_count - fixed_25k_count}개의 폴리곤이 손실됨")
            
            # 병합 실행
            self.debug_print("수정된 레이어 병합 중...")
            params = {
                'LAYERS': [fixed_5k, fixed_25k],
                'CRS': layer_5k.crs(),
                'OUTPUT': 'memory:'  # 메모리 레이어로 직접 생성
            }
            
            result = processing.run("native:mergevectorlayers", params)
            final_layer = result['OUTPUT']
            
            if isinstance(final_layer, str):
                final_layer = QgsVectorLayer(final_layer, "final_merged_result", "ogr")
            else:
                final_layer.setName("final_merged_result")
            
            # 병합 후 피처 수 확인
            merged_count = final_layer.featureCount()
            expected_count = fixed_5k_count + fixed_25k_count
            self.debug_print(f"병합 후 피처 수: {merged_count}, 예상 피처 수: {expected_count}")
            
            if merged_count < expected_count:
                self.debug_print(f"경고: 병합 과정에서 {expected_count - merged_count}개의 폴리곤이 손실됨")
            
            # ===== 중복 지오메트리 제거 과정을 완전히 제거함 =====
            self.debug_print("중복 지오메트리 제거 과정을 건너뜁니다.")
            
            # 프로젝트에 추가
            QgsProject.instance().addMapLayer(final_layer)
            
            # 최종 피처 수 확인
            final_count = final_layer.featureCount()
            self.debug_print(f"최종 피처 수: {final_count}")
            self.debug_print(f"최종 레이어 병합 완료: {final_layer.name()}")
            
            return final_layer
            
        except Exception as e:
            self.debug_print(f"최종 레이어 병합 중 오류: {str(e)}")
            print(traceback.format_exc())
            self.iface.messageBar().pushMessage("오류", f"최종 레이어 병합 중 오류: {str(e)}", level=Qgis.Critical)
            return None

    def invert_polygon(self, layer, boundary_layer):
        """폴리곤을 주어진 경계 내에서 반전"""
        try:
            self.debug_print(f"========== 폴리곤 반전 시작: {layer.name()} ==========")
            
            # difference 도구를 사용하여 반전
            params = {
                'INPUT': boundary_layer,
                'OVERLAY': layer,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            }
            
            result = processing.run("native:difference", params)
            inverted_layer = result['OUTPUT']
            
            if isinstance(inverted_layer, str):
                inverted_layer = QgsVectorLayer(inverted_layer, f"{layer.name()}_inverted", "ogr")
            else:
                inverted_layer.setName(f"{layer.name()}_inverted")
            
            # 프로젝트에 추가
            QgsProject.instance().addMapLayer(inverted_layer)
            
            self.debug_print(f"폴리곤 반전 완료: {inverted_layer.name()}")
            return inverted_layer
            
        except Exception as e:
            self.debug_print(f"폴리곤 반전 중 오류: {str(e)}")
            print(traceback.format_exc())
            self.iface.messageBar().pushMessage("오류", f"폴리곤 반전 중 오류: {str(e)}", level=Qgis.Critical)
            return None

    def explode_multipolygons(self, layer):
        """멀티폴리곤을 개별 폴리곤으로 분리"""
        try:
            self.debug_print(f"========== 멀티폴리곤 분리 시작: {layer.name()} ==========")
            self.debug_print(f"입력 피처 수: {layer.featureCount()}")
            
            # 원본 레이어 정보 미리 저장
            original_layer_name = layer.name()
            original_layer_id = layer.id()
            
            # multiparttosingleparts 알고리즘 실행
            params = {
                'INPUT': layer,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            }
            
            result = processing.run("native:multiparttosingleparts", params)
            exploded_layer = result['OUTPUT']
            
            if isinstance(exploded_layer, str):
                exploded_layer = QgsVectorLayer(exploded_layer, f"{original_layer_name}_exploded", "ogr")
            else:
                exploded_layer.setName(f"{original_layer_name}_exploded")
            
            self.debug_print(f"멀티폴리곤 분리 후 피처 수: {exploded_layer.featureCount()}")
            
            # 원본 레이어 제거
            if QgsProject.instance().mapLayer(original_layer_id):
                QgsProject.instance().removeMapLayer(original_layer_id)
                self.debug_print(f"원본 레이어 {original_layer_name} 제거 완료")
            
            # 새 레이어 추가
            QgsProject.instance().addMapLayer(exploded_layer)
            self.debug_print(f"멀티폴리곤 분리 완료: {exploded_layer.name()}")
            
            return exploded_layer
            
        except Exception as e:
            self.debug_print(f"멀티폴리곤 분리 중 오류: {str(e)}")
            print(traceback.format_exc())
            self.iface.messageBar().pushMessage("오류", f"멀티폴리곤 분리 중 오류: {str(e)}", level=Qgis.Critical)
            return layer

    def clean_merged_geometry(self, geometry):
        """병합된 지오메트리에서 내부 선 및 불필요한 요소 제거 - 버퍼 기법 강화"""
        try:
            if geometry.type() != QgsWkbTypes.PolygonGeometry:
                return geometry
            
            # 먼저 기본적인 유효성 검사 및 수정
            if not geometry.isGeosValid():
                geometry = geometry.makeValid()
                if not geometry.isGeosValid():
                    return geometry  # 수정 불가능한 경우 원본 반환
            
            # 원본 면적 저장
            original_area = geometry.area()
            
            # 버퍼 기법으로 내부 선 제거
            # 1. 작은 양의 버퍼로 확장
            buffered_geom = geometry.buffer(0.01, 5)
            
            # 2. 같은 양의 음의 버퍼로 축소하여 원래 크기로
            cleaned_geom = buffered_geom.buffer(-0.01, 5)
            
            # 3. 추가적인 buffer(0) 처리로 정리
            cleaned_geom = cleaned_geom.buffer(0, 5)
            
            # 4. 미세한 단순화로 불필요한 꼭지점 제거
            cleaned_geom = cleaned_geom.simplify(0.001)
            
            # 5. 유효성 검사
            if not cleaned_geom.isGeosValid():
                cleaned_geom = cleaned_geom.makeValid()
            
            # 면적 변화 확인 (너무 많이 변하지 않도록)
            if cleaned_geom.isGeosValid() and not cleaned_geom.isEmpty():
                new_area = cleaned_geom.area()
                # 면적 차이가 1% 이내인 경우만 정리된 지오메트리 사용
                if abs(new_area - original_area) / original_area < 0.01:
                    return cleaned_geom
                else:
                    self.debug_print(f"정리 후 면적 변화가 너무 큼: {abs(new_area - original_area) / original_area * 100}%")
            
            # 정리가 실패한 경우 원본 반환
            return geometry
            
        except Exception as e:
            self.debug_print(f"지오메트리 정리 중 오류: {str(e)}")
            return geometry

    def merge_features_by_attribute_condition(self, layer):
        """FRTP_NM과 L2_NAME 조건에 따라 피처 병합 - 다중 인접 피처 처리 및 지오메트리 정리"""
        try:
            self.debug_print(f"========== 속성 조건에 따른 피처 병합 시작: {layer.name()} ==========")
            
            # 필드 인덱스 확인
            frtp_nm_idx = layer.fields().indexFromName("FRTP_NM")
            l2_name_idx = layer.fields().indexFromName("L2_NAME")
            
            if frtp_nm_idx == -1 or l2_name_idx == -1:
                self.debug_print("FRTP_NM 또는 L2_NAME 필드가 없습니다.")
                return layer
            
            # 편집 모드 시작
            if not layer.startEditing():
                self.debug_print("편집 모드 시작 실패")
                return layer
            
            # 피처들을 그룹으로 분류
            features_by_value = {}  # 값별로 피처 그룹화
            features_dict = {}
            
            self.debug_print("피처 분류 시작...")
            for feature in layer.getFeatures():
                fid = feature.id()
                frtp_nm = feature[frtp_nm_idx]
                l2_name = feature[l2_name_idx]
                
                features_dict[fid] = feature
                
                # FRTP_NM이 NULL이고 L2_NAME에 데이터가 있는 경우
                if (frtp_nm is None or frtp_nm == NULL) and l2_name and l2_name != NULL:
                    if l2_name not in features_by_value:
                        features_by_value[l2_name] = {'group_a': [], 'group_b': []}
                    features_by_value[l2_name]['group_a'].append(fid)
                    self.debug_print(f"Group A 피처 발견: ID={fid}, L2_NAME={l2_name}")
                
                # FRTP_NM에 데이터가 있고 L2_NAME이 NULL인 경우
                elif frtp_nm and frtp_nm != NULL and (l2_name is None or l2_name == NULL):
                    if frtp_nm not in features_by_value:
                        features_by_value[frtp_nm] = {'group_a': [], 'group_b': []}
                    features_by_value[frtp_nm]['group_b'].append(fid)
                    self.debug_print(f"Group B 피처 발견: ID={fid}, FRTP_NM={frtp_nm}")
            
            self.debug_print(f"총 {len(features_by_value)}개의 고유 값 발견")
            
            # 공간 인덱스 생성
            spatial_index = QgsSpatialIndex()
            for fid in features_dict.keys():
                feature = features_dict[fid]
                spatial_index.addFeature(feature)
            
            # 연결된 피처 클러스터 찾기
            def find_connected_cluster(start_fid, value, visited):
                """BFS를 사용하여 연결된 피처 클러스터 찾기"""
                cluster = {'group_a': [], 'group_b': []}
                queue = [start_fid]
                
                while queue:
                    current_fid = queue.pop(0)
                    if current_fid in visited:
                        continue
                    
                    visited.add(current_fid)
                    current_feature = features_dict[current_fid]
                    current_geom = current_feature.geometry()
                    
                    # 현재 피처가 어느 그룹인지 확인
                    if current_fid in features_by_value[value]['group_a']:
                        cluster['group_a'].append(current_fid)
                    elif current_fid in features_by_value[value]['group_b']:
                        cluster['group_b'].append(current_fid)
                    else:
                        continue
                    
                    # 인접한 피처 찾기
                    search_buffer = current_geom.buffer(0.001, 5)
                    candidates = spatial_index.intersects(search_buffer.boundingBox())
                    
                    for candidate_id in candidates:
                        if candidate_id in visited:
                            continue
                        
                        # 같은 값을 가진 피처만 고려
                        if (candidate_id in features_by_value[value]['group_a'] or 
                            candidate_id in features_by_value[value]['group_b']):
                            
                            candidate_geom = features_dict[candidate_id].geometry()
                            
                            # 인접 여부 확인
                            is_adjacent = False
                            if current_geom.touches(candidate_geom):
                                is_adjacent = True
                            else:
                                distance = current_geom.distance(candidate_geom)
                                if distance < 0.0001:
                                    is_adjacent = True
                                else:
                                    intersection = current_geom.intersection(candidate_geom)
                                    if not intersection.isEmpty():
                                        is_adjacent = True
                            
                            if is_adjacent:
                                queue.append(candidate_id)
                
                return cluster
            
            # 병합할 클러스터 찾기
            merge_clusters = []
            visited_features = set()
            
            self.debug_print("병합할 클러스터 찾기 시작...")
            for value, groups in features_by_value.items():
                if not groups['group_a'] or not groups['group_b']:
                    continue
                
                # 각 값에 대해 클러스터 찾기
                for fid in groups['group_a'] + groups['group_b']:
                    if fid not in visited_features:
                        cluster = find_connected_cluster(fid, value, visited_features)
                        
                        # 클러스터에 group_a와 group_b 피처가 모두 있는 경우만 병합
                        if cluster['group_a'] and cluster['group_b']:
                            merge_clusters.append({
                                'value': value,
                                'features': cluster['group_a'] + cluster['group_b'],
                                'group_a': cluster['group_a'],
                                'group_b': cluster['group_b']
                            })
                            self.debug_print(f"병합 클러스터 발견: {value} - A그룹 {len(cluster['group_a'])}개, B그룹 {len(cluster['group_b'])}개")
            
            self.debug_print(f"총 {len(merge_clusters)}개의 병합 클러스터 발견")
            
            # 클러스터 병합 수행
            success_count = 0
            for cluster in merge_clusters:
                try:
                    # 임시 레이어 생성
                    temp_layer = QgsVectorLayer(f"Polygon?crs={layer.crs().authid()}", "temp", "memory")
                    temp_provider = temp_layer.dataProvider()
                    
                    # 필드 구조 복사
                    temp_provider.addAttributes(layer.fields())
                    temp_layer.updateFields()
                    
                    # 클러스터의 모든 피처를 임시 레이어에 추가 (지오메트리 검증 포함)
                    temp_features = []
                    for fid in cluster['features']:
                        feature = features_dict[fid]
                        geom = feature.geometry()
                        
                        # 지오메트리 유효성 검사 및 수정
                        if not geom.isGeosValid():
                            self.debug_print(f"피처 {fid}의 지오메트리가 유효하지 않음, 수정 시도")
                            geom = geom.makeValid()
                            
                            if not geom.isGeosValid():
                                self.debug_print(f"피처 {fid} 수정 실패, 건너뜀")
                                continue
                        
                        # 임시 피처 생성
                        temp_feature = QgsFeature(feature)
                        temp_feature.setGeometry(geom)
                        temp_features.append(temp_feature)
                    
                    if not temp_features:
                        self.debug_print(f"클러스터 {cluster['value']}에 유효한 피처가 없음")
                        continue
                    
                    temp_provider.addFeatures(temp_features)
                    
                    # dissolve 수행
                    params = {
                        'INPUT': temp_layer,
                        'FIELD': [],  # 모든 피처를 하나로 병합
                        'OUTPUT': 'TEMPORARY_OUTPUT'
                    }
                    
                    result = processing.run("native:dissolve", params)
                    dissolved_layer = result['OUTPUT']
                    
                    if isinstance(dissolved_layer, str):
                        dissolved_layer = QgsVectorLayer(dissolved_layer, "dissolved", "ogr")
                    
                    # dissolve 결과 가져오기
                    dissolved_features = list(dissolved_layer.getFeatures())
                    if len(dissolved_features) > 0:
                        dissolved_feature = dissolved_features[0]
                        merged_geom = dissolved_feature.geometry()
                        
                        # 병합된 지오메트리 정리
                        cleaned_geom = self.clean_merged_geometry(merged_geom)
                        
                        # 정리 후에도 폴리곤이 유효한지 확인
                        if not cleaned_geom.isEmpty() and cleaned_geom.area() > 0 and cleaned_geom.isGeosValid():
                            merged_geom = cleaned_geom
                            self.debug_print(f"클러스터 {cluster['value']} 지오메트리 정리 성공")
                        else:
                            self.debug_print("정리 후 폴리곤이 유효하지 않음, dissolve 결과 사용")
                            # dissolve 결과에 직접 버퍼 처리
                            buffer_geom = merged_geom.buffer(0.01, 5).buffer(-0.01, 5).buffer(0, 5)
                            if buffer_geom.isGeosValid() and not buffer_geom.isEmpty():
                                merged_geom = buffer_geom
                                self.debug_print(f"클러스터 {cluster['value']} 버퍼 처리로 내부 선 제거 성공")
                        
                        if merged_geom.isGeosValid() and not merged_geom.isEmpty():
                            # group_b의 첫 번째 피처를 기준으로 속성 설정
                            base_feature = features_dict[cluster['group_b'][0]]
                            new_feature = QgsFeature(layer.fields())
                            new_feature.setGeometry(merged_geom)
                            
                            # 속성 복사 (group_b 우선)
                            for i in range(layer.fields().count()):
                                field_name = layer.fields()[i].name()
                                if field_name == "L2_NAME":
                                    # L2_NAME은 group_a의 값을 사용
                                    a_feature = features_dict[cluster['group_a'][0]]
                                    new_feature.setAttribute(i, a_feature[i])
                                else:
                                    # 나머지 속성은 group_b의 값을 사용
                                    new_feature.setAttribute(i, base_feature[i])
                            
                            # 새 피처 추가
                            layer.addFeature(new_feature)
                            
                            # 기존 피처들 삭제
                            for fid in cluster['features']:
                                layer.deleteFeature(fid)
                            
                            self.debug_print(f"클러스터 {cluster['value']} dissolve 및 정리 완료: {len(cluster['features'])}개 피처 병합")
                            success_count += 1
                        else:
                            self.debug_print(f"클러스터 {cluster['value']} 병합 실패: 유효하지 않거나 비어있는 지오메트리")
                    else:
                        self.debug_print(f"클러스터 {cluster['value']} dissolve 실패: 결과 피처 없음")
                        
                except Exception as e:
                    self.debug_print(f"클러스터 {cluster['value']} dissolve 중 오류: {str(e)}")
            
            # 변경사항 저장
            if layer.commitChanges():
                self.debug_print(f"속성 조건에 따른 피처 병합 완료: {success_count}개 클러스터 병합 성공 (총 {len(merge_clusters)}개 시도)")
                return layer
            else:
                self.debug_print("병합 작업 저장 실패")
                layer.rollBack()
                return layer
        
        except Exception as e:
            self.debug_print(f"속성 조건에 따른 피처 병합 중 오류: {str(e)}")
            print(traceback.format_exc())
            if layer.isEditable():
                layer.rollBack()
            self.iface.messageBar().pushMessage("오류", f"속성 조건에 따른 피처 병합 중 오류: {str(e)}", level=Qgis.Critical)
            return layer