"""
MyTalk - 탭별 개별 생성 버전
주요 수정사항:
1. 탭 구성 변경: 원본 스크립트, 기초 말하기, TED, PODCAST, DIALOG
2. 기초 말하기 추가 (영어 초보자용 5문장)
3. 각 탭마다 개별 (스크립트 작성), (음성 작성) 버튼
4. 자동 생성 대신 사용자 선택 기반 생성
5. imageio_ffmpeg를 사용한 오디오 합치기 (Streamlit Cloud 호환)
"""

import streamlit as st
import os
import json
import tempfile
from PIL import Image
import time
import uuid
import shutil
from pathlib import Path
from datetime import datetime
import re
import subprocess
import base64

# OpenAI Library
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    st.error("OpenAI 라이브러리가 필요합니다. pip install openai로 설치해주세요.")

# imageio_ffmpeg for Streamlit Cloud compatibility
try:
    import imageio_ffmpeg as ffmpeg
    FFMPEG_AVAILABLE = True
    # ffmpeg 실행 파일 경로 가져오기
    FFMPEG_PATH = ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG_AVAILABLE = False
    FFMPEG_PATH = None

# pydub as fallback
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False


class SimpleStorage:
    """간소화된 로컬 파일 저장소 - 개선된 오디오 구조 지원"""
    
    def __init__(self, base_dir="mytalk_data"):
        self.base_dir = Path(base_dir)
        self.scripts_dir = self.base_dir / "scripts"
        self.audio_dir = self.base_dir / "audio"
        
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
    
    def sanitize_filename(self, filename):
        """안전한 파일명 생성"""
        safe_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_() "
        safe_filename = ''.join(c for c in filename if c in safe_chars)
        safe_filename = ' '.join(safe_filename.split())[:50]
        return safe_filename.strip() or "Untitled"
    
    def save_or_update_project(self, results, input_content, input_method, category, project_id=None, existing_project_folder=None):
        """프로젝트를 파일로 저장하거나 기존 프로젝트에 업데이트 - 개선된 오디오 구조 지원"""
        try:
            # 기존 프로젝트 폴더가 있으면 사용, 없으면 새로 생성
            if existing_project_folder and os.path.exists(existing_project_folder):
                project_folder = Path(existing_project_folder)
                # 기존 메타데이터 로드
                metadata_file = project_folder / "metadata.json"
                if metadata_file.exists():
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                else:
                    # 메타데이터가 없으면 새로 생성
                    metadata = {
                        'project_id': project_id,
                        'title': results.get('title', f'Script_{project_id}'),
                        'category': category,
                        'input_method': input_method,
                        'input_content': input_content,
                        'created_at': datetime.now().isoformat(),
                        'versions': [],
                        'saved_files': {}
                    }
                st.write(f"📁 기존 프로젝트 폴더 사용: {project_folder.name}")
            else:
                # 새 프로젝트 폴더 생성
                if not project_id:
                    project_id = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                title = results.get('title', f'Script_{project_id}')
                safe_title = self.sanitize_filename(title)
                project_folder = self.scripts_dir / f"{project_id}_{safe_title}"
                project_folder.mkdir(exist_ok=True)
                
                metadata = {
                    'project_id': project_id,
                    'title': title,
                    'category': category,
                    'input_method': input_method,
                    'input_content': input_content,
                    'created_at': datetime.now().isoformat(),
                    'versions': [],
                    'saved_files': {}
                }
                st.write(f"📁 새 프로젝트 폴더 생성: {project_folder.name}")
            
            audio_folder = project_folder / "audio"
            audio_folder.mkdir(exist_ok=True)
            
            # 원본 스크립트 저장
            if 'original_script' in results:
                original_file = project_folder / "original_script.txt"
                with open(original_file, 'w', encoding='utf-8') as f:
                    f.write(results['original_script'])
                metadata['saved_files']['original_script'] = str(original_file)
                if 'original' not in metadata['versions']:
                    metadata['versions'].append('original')
                st.write(f"✅ 원본 스크립트 저장: {original_file.name}")
            
            # 한국어 번역 저장
            if 'korean_translation' in results:
                translation_file = project_folder / "korean_translation.txt"
                with open(translation_file, 'w', encoding='utf-8') as f:
                    f.write(results['korean_translation'])
                metadata['saved_files']['korean_translation'] = str(translation_file)
                st.write(f"✅ 한국어 번역 저장: {translation_file.name}")
            
            # 각 버전별 스크립트 및 오디오 저장
            versions = ['basic', 'ted', 'podcast', 'dialog']
            
            for version in versions:
                script_key = f"{version}_script"
                audio_key = f"{version}_audio"
                translation_key = f"{version}_korean_translation"
                
                if script_key in results and results[script_key]:
                    script_file = project_folder / f"{version}_script.txt"
                    with open(script_file, 'w', encoding='utf-8') as f:
                        f.write(results[script_key])
                    metadata['saved_files'][script_key] = str(script_file)
                    if version not in metadata['versions']:
                        metadata['versions'].append(version)
                    st.write(f"✅ {version.upper()} 스크립트 저장: {script_file.name}")
                
                # 한국어 번역 저장
                if translation_key in results and results[translation_key]:
                    translation_file = project_folder / f"{version}_korean_translation.txt"
                    with open(translation_file, 'w', encoding='utf-8') as f:
                        f.write(results[translation_key])
                    metadata['saved_files'][translation_key] = str(translation_file)
                    st.write(f"✅ {version.upper()} 한국어 번역 저장: {translation_file.name}")
                
                # 개선된 오디오 파일들 저장
                if audio_key in results and results[audio_key]:
                    audio_data = results[audio_key]
                    
                    # 단일 오디오 파일인 경우
                    if isinstance(audio_data, str) and os.path.exists(audio_data):
                        audio_ext = Path(audio_data).suffix or '.mp3'
                        audio_dest = audio_folder / f"{version}_audio{audio_ext}"
                        shutil.copy2(audio_data, audio_dest)
                        metadata['saved_files'][audio_key] = str(audio_dest)
                        st.write(f"✅ {version.upper()} 오디오 저장: {audio_dest.name}")
                    
                    # 다중 오디오 파일인 경우 (새로운 구조)
                    elif isinstance(audio_data, dict):
                        audio_paths = {}
                        
                        # 통합 대화 오디오 저장 (merged)
                        if 'merged' in audio_data and isinstance(audio_data['merged'], str) and os.path.exists(audio_data['merged']):
                            audio_ext = Path(audio_data['merged']).suffix or '.mp3'
                            merged_dest = audio_folder / f"{version}_merged_dialogue{audio_ext}"
                            shutil.copy2(audio_data['merged'], merged_dest)
                            audio_paths['merged'] = str(merged_dest)
                            st.write(f"✅ {version.upper()} 통합 대화 오디오 저장: {merged_dest.name}")
                        
                        # 문장별 오디오들 저장 (sentences)
                        if 'sentences' in audio_data and isinstance(audio_data['sentences'], list):
                            sentences_folder = audio_folder / f"{version}_sentences"
                            sentences_folder.mkdir(exist_ok=True)
                            
                            sentence_paths = []
                            for i, sentence_info in enumerate(audio_data['sentences']):
                                if isinstance(sentence_info, dict) and 'audio_file' in sentence_info:
                                    audio_file = sentence_info['audio_file']
                                    if isinstance(audio_file, str) and os.path.exists(audio_file):
                                        role = sentence_info.get('role', 'unknown')
                                        voice = sentence_info.get('voice', 'unknown')
                                        
                                        audio_ext = Path(audio_file).suffix or '.mp3'
                                        sentence_dest = sentences_folder / f"{i+1:02d}_{role}_{voice}{audio_ext}"
                                        shutil.copy2(audio_file, sentence_dest)
                                        
                                        sentence_info_copy = sentence_info.copy()
                                        sentence_info_copy['audio_file'] = str(sentence_dest)
                                        sentence_paths.append(sentence_info_copy)
                            
                            if sentence_paths:
                                audio_paths['sentences'] = sentence_paths
                                st.write(f"✅ {version.upper()} {len(sentence_paths)}개 문장별 오디오 저장")
                        
                        # 기존 역할별 오디오도 저장 (host, guest, a, b)
                        role_keys = ['host', 'guest', 'a', 'b']
                        for role in role_keys:
                            if role in audio_data and isinstance(audio_data[role], str) and os.path.exists(audio_data[role]):
                                audio_ext = Path(audio_data[role]).suffix or '.mp3'
                                role_dest = audio_folder / f"{version}_audio_{role}{audio_ext}"
                                shutil.copy2(audio_data[role], role_dest)
                                audio_paths[role] = str(role_dest)
                                st.write(f"✅ {version.upper()} {role.upper()} 오디오 저장: {role_dest.name}")
                        
                        if audio_paths:
                            metadata['saved_files'][audio_key] = audio_paths
                    
                    # 리스트나 다른 형태인 경우 (오류 방지)
                    else:
                        st.warning(f"⚠️ {version.upper()} 오디오 데이터 형식을 인식할 수 없습니다: {type(audio_data)}")
            
            # 원본 오디오 저장
            if 'original_audio' in results and results['original_audio']:
                audio_src = results['original_audio']
                if isinstance(audio_src, str) and os.path.exists(audio_src):
                    audio_ext = Path(audio_src).suffix or '.mp3'
                    audio_dest = audio_folder / f"original_audio{audio_ext}"
                    shutil.copy2(audio_src, audio_dest)
                    metadata['saved_files']['original_audio'] = str(audio_dest)
                    st.write(f"✅ 원본 오디오 저장: {audio_dest.name}")
            
            # 메타데이터 최종 저장
            metadata['updated_at'] = datetime.now().isoformat()
            metadata_file = project_folder / "metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            # 프로젝트 인덱스 업데이트 (기존 프로젝트면 업데이트만, 새 프로젝트면 추가)
            self.update_project_index(metadata['project_id'], metadata['title'], category, str(project_folder), update_existing=bool(existing_project_folder))
            
            st.success(f"🎉 파일 저장 완료! 프로젝트 폴더: {project_folder.name}")
            st.success(f"📊 저장된 버전: {len(set(metadata['versions']))}개")
            
            # 저장된 파일들 요약 정보 표시
            with st.expander("📋 저장된 파일 상세 목록", expanded=False):
                for file_type, file_info in metadata['saved_files'].items():
                    if isinstance(file_info, str):
                        st.write(f"• {file_type}: {os.path.basename(file_info)}")
                    elif isinstance(file_info, dict):
                        st.write(f"• {file_type}:")
                        for sub_key, sub_info in file_info.items():
                            if isinstance(sub_info, str):
                                st.write(f"  - {sub_key}: {os.path.basename(sub_info)}")
                            elif isinstance(sub_info, list):
                                st.write(f"  - {sub_key}: {len(sub_info)}개 파일")
            
            return metadata['project_id'], str(project_folder)
            
        except Exception as e:
            st.error(f"⛔ 파일 저장 실패: {str(e)}")
            import traceback
            st.error(f"상세 오류 정보:\n{traceback.format_exc()}")
            return None, None
    
    def update_project_index(self, project_id, title, category, project_path, update_existing=False):
        """프로젝트 인덱스 업데이트 - 기존 프로젝트는 업데이트만"""
        try:
            index_file = self.base_dir / "project_index.json"
            
            if index_file.exists():
                with open(index_file, 'r', encoding='utf-8') as f:
                    index_data = json.load(f)
            else:
                index_data = {"projects": []}
            
            # 기존 프로젝트 찾기
            existing_project = None
            for i, project in enumerate(index_data["projects"]):
                if project['project_id'] == project_id:
                    existing_project = i
                    break
            
            if update_existing and existing_project is not None:
                # 기존 프로젝트 업데이트
                index_data["projects"][existing_project]['title'] = title
                index_data["projects"][existing_project]['category'] = category
                index_data["projects"][existing_project]['updated_at'] = datetime.now().isoformat()
                st.write(f"📝 기존 프로젝트 정보 업데이트: {title}")
            elif existing_project is None:
                # 새 프로젝트 추가
                new_project = {
                    'project_id': project_id,
                    'title': title,
                    'category': category,
                    'project_path': project_path,
                    'created_at': datetime.now().isoformat()
                }
                
                index_data["projects"].append(new_project)
                index_data["projects"].sort(key=lambda x: x['created_at'], reverse=True)
                st.write(f"📝 새 프로젝트 인덱스 추가: {title}")
            
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)
            
            return True
            
        except Exception as e:
            st.error(f"인덱스 업데이트 실패: {str(e)}")
            return False
    
    def load_all_projects(self):
        """모든 프로젝트 로드"""
        try:
            index_file = self.base_dir / "project_index.json"
            
            if not index_file.exists():
                return []
            
            with open(index_file, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
            
            projects = []
            for project_info in index_data.get("projects", []):
                project_path = Path(project_info['project_path'])
                
                if project_path.exists():
                    metadata_file = project_path / "metadata.json"
                    if metadata_file.exists():
                        with open(metadata_file, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                        projects.append(metadata)
            
            return projects
            
        except Exception as e:
            st.error(f"프로젝트 로드 실패: {str(e)}")
            return []
    
    def load_project_content(self, project_id):
        """특정 프로젝트의 모든 내용 로드 - 개선된 오디오 구조 지원"""
        try:
            projects = self.load_all_projects()
            target_project = None
            
            for project in projects:
                if project['project_id'] == project_id:
                    target_project = project
                    break
            
            if not target_project:
                return None
            
            content = {}
            
            for file_type, file_info in target_project['saved_files'].items():
                # 텍스트 파일들 (스크립트, 번역)
                if 'script' in file_type or 'translation' in file_type:
                    if isinstance(file_info, str) and os.path.exists(file_info):
                        with open(file_info, 'r', encoding='utf-8') as f:
                            content[file_type] = f.read()
                
                # 오디오 파일들
                elif 'audio' in file_type:
                    # 단일 파일인 경우
                    if isinstance(file_info, str) and os.path.exists(file_info):
                        content[file_type] = file_info
                    
                    # 다중 파일인 경우 (새로운 구조)
                    elif isinstance(file_info, dict):
                        audio_data = {}
                        
                        # 통합 대화 오디오
                        if 'merged' in file_info and isinstance(file_info['merged'], str) and os.path.exists(file_info['merged']):
                            audio_data['merged'] = file_info['merged']
                        
                        # 문장별 오디오들
                        if 'sentences' in file_info and isinstance(file_info['sentences'], list):
                            valid_sentences = []
                            for sentence_info in file_info['sentences']:
                                if isinstance(sentence_info, dict) and 'audio_file' in sentence_info:
                                    if isinstance(sentence_info['audio_file'], str) and os.path.exists(sentence_info['audio_file']):
                                        valid_sentences.append(sentence_info)
                            if valid_sentences:
                                audio_data['sentences'] = valid_sentences
                        
                        # 기존 역할별 오디오들
                        for role in ['host', 'guest', 'a', 'b']:
                            if role in file_info and isinstance(file_info[role], str) and os.path.exists(file_info[role]):
                                audio_data[role] = file_info[role]
                        
                        if audio_data:
                            content[file_type] = audio_data
            
            content['metadata'] = target_project
            
            return content
            
        except Exception as e:
            st.error(f"프로젝트 내용 로드 실패: {str(e)}")
            import traceback
            st.error(f"상세 오류:\n{traceback.format_exc()}")
            return None
    
    def delete_project(self, project_id):
        """프로젝트 완전 삭제"""
        try:
            projects = self.load_all_projects()
            target_project = None
            
            for project in projects:
                if project['project_id'] == project_id:
                    target_project = project
                    break
            
            if target_project:
                project_path = Path(list(target_project['saved_files'].values())[0]).parent
                if project_path.exists():
                    shutil.rmtree(project_path)
                
                index_file = self.base_dir / "project_index.json"
                if index_file.exists():
                    with open(index_file, 'r', encoding='utf-8') as f:
                        index_data = json.load(f)
                    
                    index_data["projects"] = [p for p in index_data["projects"] if p['project_id'] != project_id]
                    
                    with open(index_file, 'w', encoding='utf-8') as f:
                        json.dump(index_data, f, ensure_ascii=False, indent=2)
                
                return True
            
            return False
            
        except Exception as e:
            st.error(f"프로젝트 삭제 실패: {str(e)}")
            return False


class SimpleLLMProvider:
    def __init__(self, api_key, model):
        self.api_key = api_key
        self.model = model
        self.client = None
        self.setup_client()
    
    def setup_client(self):
        """클라이언트 초기화"""
        try:
            if OPENAI_AVAILABLE and self.api_key:
                self.client = openai.OpenAI(api_key=self.api_key)
        except Exception as e:
            st.error(f"LLM 클라이언트 초기화 실패: {str(e)}")
    
    def generate_content(self, prompt):
        """간단한 콘텐츠 생성"""
        try:
            if not self.client or not self.api_key:
                return None
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.7
            )
            return response.choices[0].message.content
        
        except Exception as e:
            st.error(f"LLM 호출 실패: {str(e)}")
            return None


def generate_audio_with_openai_tts(text, api_key, voice='alloy'):
    """OpenAI TTS API를 사용한 음성 생성"""
    try:
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI 라이브러리가 설치되지 않았습니다")
        
        if not text or not text.strip():
            st.warning(f"빈 텍스트로 인해 {voice} 음성 생성을 건너뜁니다.")
            return None
        
        # OpenAI 클라이언트 설정
        client = openai.OpenAI(api_key=api_key)
        
        # TTS 요청
        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text.strip()
        )
        
        # 임시 파일에 저장 (스트림 경고 해결)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
        
        # 응답 내용을 직접 쓰기
        with open(temp_file.name, 'wb') as f:
            for chunk in response.iter_bytes(chunk_size=1024):
                f.write(chunk)
        
        temp_file.close()
        
        # 파일이 생성되었는지 확인
        if os.path.exists(temp_file.name) and os.path.getsize(temp_file.name) > 0:
            return temp_file.name
        else:
            st.error(f"음성 파일 생성 실패: {voice}")
            return None
        
    except Exception as e:
        st.error(f"OpenAI TTS 생성 실패 ({voice}): {str(e)}")
        return None


def clean_text_for_tts(text):
    """TTS를 위한 텍스트 정리 - 개선된 버전"""
    try:
        if not text or not isinstance(text, str):
            return ""
        
        # [ ... ] 로 둘러싸인 부분 제거 (지침이나 메타 정보)
        text = re.sub(r'\[.*?\]', '', text)
        
        # ** ... ** 로 둘러싸인 부분 제거 (볼드 텍스트)
        text = re.sub(r'\*\*.*?\*\*', '', text)
        
        # * ... * 로 둘러싸인 부분 제거 (이탤릭)
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        
        # 마크다운 헤더 제거 (###, ##, # 등)
        text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
        
        # 줄바꿈을 공백으로 변경
        text = text.replace('\n', ' ')
        text = text.replace('\r', ' ')
        
        # 여러 공백을 단일 공백으로 변경
        text = re.sub(r'\s+', ' ', text)
        
        # 앞뒤 공백 제거
        text = text.strip()
        
        return text
        
    except Exception as e:
        st.warning(f"텍스트 정리 중 오류: {str(e)}")
        return text if text else ""


def extract_role_dialogues(text, version_type):
    """역할별 대화 추출 및 정리 (개선된 버전)"""
    try:
        if not text or not isinstance(text, str):
            st.error("유효하지 않은 텍스트입니다.")
            return None
            
        st.write(f"🔍 텍스트 분석 시작...")
        st.write(f"📄 원본 텍스트 길이: {len(text)} 글자")
        
        dialogue_sequence = []  # (role, content, order) 튜플의 리스트
        
        if version_type == 'podcast':
            # Host, Guest 역할 분리 (순서 보존)
            lines = text.split('\n')
            order = 0
            host_texts = []
            guest_texts = []
            
            for line in lines:
                line = line.strip()
                if not line:  # 빈 줄 건너뛰기
                    continue
                    
                # Host로 시작하는 줄 찾기
                if line.lower().startswith('host:'):
                    content = line[5:].strip()  # 'host:' 제거
                    content = clean_text_for_tts(content)
                    if content:
                        dialogue_sequence.append(('host', content, order))
                        host_texts.append(content)
                        order += 1
                        
                # Guest로 시작하는 줄 찾기
                elif line.lower().startswith('guest:'):
                    content = line[6:].strip()  # 'guest:' 제거
                    content = clean_text_for_tts(content)
                    if content:
                        dialogue_sequence.append(('guest', content, order))
                        guest_texts.append(content)
                        order += 1
                        
                # Host나 Guest가 명시되지 않은 경우도 처리
                elif ':' in line:
                    parts = line.split(':', 1)
                    role = parts[0].strip().lower()
                    content = parts[1].strip()
                    
                    if 'host' in role or 'presenter' in role or 'interviewer' in role:
                        content = clean_text_for_tts(content)
                        if content:
                            dialogue_sequence.append(('host', content, order))
                            host_texts.append(content)
                            order += 1
                    elif 'guest' in role or 'interviewee' in role or 'speaker' in role:
                        content = clean_text_for_tts(content)
                        if content:
                            dialogue_sequence.append(('guest', content, order))
                            guest_texts.append(content)
                            order += 1
            
            # 결과가 없으면 전체 텍스트를 Host로 할당
            if not host_texts and not guest_texts:
                st.warning("Host/Guest 구분을 찾을 수 없어 전체를 Host로 처리합니다.")
                cleaned_text = clean_text_for_tts(text)
                if cleaned_text:
                    host_texts = [cleaned_text]
                    dialogue_sequence = [('host', cleaned_text, 0)]
            
            # 디버깅 정보
            st.write(f"🔍 Host 대사 수: {len(host_texts)}")
            st.write(f"🔍 Guest 대사 수: {len(guest_texts)}")
            
            if host_texts:
                st.write(f"🔍 Host 첫 대사 미리보기: {host_texts[0][:100]}...")
            if guest_texts:
                st.write(f"🔍 Guest 첫 대사 미리보기: {guest_texts[0][:100]}...")
            
            # 역할별로 분리된 텍스트와 순서 정보 반환
            return {
                'host': ' '.join(host_texts),
                'guest': ' '.join(guest_texts),
                'sequence': dialogue_sequence
            }
        
        elif version_type == 'dialog':
            # A, B 역할 분리 (순서 보존)
            lines = text.split('\n')
            order = 0
            a_texts = []
            b_texts = []
            
            for line in lines:
                line = line.strip()
                if not line:  # 빈 줄 건너뛰기
                    continue
                    
                # A로 시작하는 줄 찾기
                if line.lower().startswith('a:'):
                    content = line[2:].strip()  # 'a:' 제거
                    content = clean_text_for_tts(content)
                    if content:
                        dialogue_sequence.append(('a', content, order))
                        a_texts.append(content)
                        order += 1
                        
                # B로 시작하는 줄 찾기
                elif line.lower().startswith('b:'):
                    content = line[2:].strip()  # 'b:' 제거
                    content = clean_text_for_tts(content)
                    if content:
                        dialogue_sequence.append(('b', content, order))
                        b_texts.append(content)
                        order += 1
                        
                # Person A, Person B 등의 변형도 처리
                elif ':' in line:
                    parts = line.split(':', 1)
                    role = parts[0].strip().lower()
                    content = parts[1].strip()
                    
                    if 'a' in role or 'person a' in role or 'speaker a' in role:
                        content = clean_text_for_tts(content)
                        if content:
                            dialogue_sequence.append(('a', content, order))
                            a_texts.append(content)
                            order += 1
                    elif 'b' in role or 'person b' in role or 'speaker b' in role:
                        content = clean_text_for_tts(content)
                        if content:
                            dialogue_sequence.append(('b', content, order))
                            b_texts.append(content)
                            order += 1
            
            # 결과가 없으면 전체 텍스트를 A로 할당
            if not a_texts and not b_texts:
                st.warning("A/B 구분을 찾을 수 없어 전체를 Person A로 처리합니다.")
                cleaned_text = clean_text_for_tts(text)
                if cleaned_text:
                    a_texts = [cleaned_text]
                    dialogue_sequence = [('a', cleaned_text, 0)]
            
            # 디버깅 정보
            st.write(f"🔍 Person A 대사 수: {len(a_texts)}")
            st.write(f"🔍 Person B 대사 수: {len(b_texts)}")
            
            if a_texts:
                st.write(f"🔍 Person A 첫 대사 미리보기: {a_texts[0][:100]}...")
            if b_texts:
                st.write(f"🔍 Person B 첫 대사 미리보기: {b_texts[0][:100]}...")
            
            # 역할별로 분리된 텍스트와 순서 정보 반환
            return {
                'a': ' '.join(a_texts),
                'b': ' '.join(b_texts),
                'sequence': dialogue_sequence
            }
        
        return None
        
    except Exception as e:
        st.error(f"역할별 대화 추출 중 오류: {str(e)}")
        import traceback
        st.error(f"상세 오류:\n{traceback.format_exc()}")
        return None


def merge_audio_files_ffmpeg(audio_files, output_file):
    """imageio_ffmpeg를 사용한 오디오 파일 합치기 (Streamlit Cloud 호환)"""
    try:
        if not FFMPEG_AVAILABLE:
            st.warning("imageio_ffmpeg가 설치되지 않았습니다.")
            return False
        
        if not audio_files:
            st.warning("합칠 오디오 파일이 없습니다.")
            return False
        
        # 임시 텍스트 파일 생성 (ffmpeg concat 용)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            concat_file = f.name
            for audio_file in audio_files:
                if os.path.exists(audio_file):
                    # 경로에 특수문자가 있을 수 있으므로 따옴표로 감싸기
                    f.write(f"file '{audio_file}'\n")
        
        try:
            # ffmpeg concat 명령어 실행
            cmd = [
                FFMPEG_PATH,
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                "-y",  # 덮어쓰기
                output_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                st.write(f"✅ ffmpeg로 {len(audio_files)}개 파일 합치기 성공")
                return True
            else:
                st.error(f"ffmpeg 오류: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            st.error("ffmpeg 실행 시간 초과")
            return False
        except Exception as e:
            st.error(f"ffmpeg 실행 오류: {str(e)}")
            return False
        finally:
            # 임시 concat 파일 정리
            if os.path.exists(concat_file):
                os.unlink(concat_file)
        
    except Exception as e:
        st.error(f"오디오 합치기 중 오류: {str(e)}")
        return False


def merge_audio_files_pydub(audio_files, silence_duration=1000):
    """pydub을 사용한 오디오 파일 합치기 (fallback)"""
    try:
        if not PYDUB_AVAILABLE:
            st.warning("pydub이 설치되지 않았습니다.")
            return None
        
        if not audio_files:
            st.warning("합칠 오디오 파일이 없습니다.")
            return None
        
        combined_audio = AudioSegment.empty()
        silence = AudioSegment.silent(duration=silence_duration)  # 1초 무음
        
        for i, audio_file in enumerate(audio_files):
            if os.path.exists(audio_file):
                try:
                    # 무음 추가 (첫 번째가 아닐 경우)
                    if i > 0:
                        combined_audio += silence
                    
                    # 오디오 세그먼트 로드 및 추가
                    audio_segment = AudioSegment.from_mp3(audio_file)
                    combined_audio += audio_segment
                    
                    st.write(f"🎶 {i+1}. {os.path.basename(audio_file)}: {len(audio_segment)}ms 추가")
                    
                except Exception as e:
                    st.warning(f"⚠️ {i+1}번째 오디오 합치기 실패: {e}")
                    continue
        
        if len(combined_audio) > 0:
            # 임시 파일에 저장
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
            combined_audio.export(temp_file.name, format="mp3")
            return temp_file.name
        else:
            st.error("⏱ 합성된 오디오가 비어있습니다.")
            return None
            
    except Exception as e:
        st.error(f"pydub 오디오 합치기 중 오류: {str(e)}")
        return None


def generate_multi_voice_audio(text, api_key, voice1, voice2, version_type):
    """다중 음성 오디오 생성 및 대화 순서 교차 합치기 - 완전히 개선된 버전"""
    try:
        st.write(f"🎵 {version_type.upper()} 음성 생성 시작...")
        
        # 입력 텍스트 검증
        if not text or not text.strip():
            st.error(f"⛔ 빈 텍스트로 인해 {version_type} 음성 생성을 건너뜁니다.")
            return None
        
        # 2인 대화인 경우 문장별 교차 처리
        if version_type in ['podcast', 'dialog']:
            st.write(f"🎭 {version_type.upper()} 대화 순서 분석 중...")
            
            role_dialogues = extract_role_dialogues(text, version_type)
            
            if not role_dialogues or 'sequence' not in role_dialogues:
                st.error(f"⛔ {version_type} 대화에서 순서 정보를 찾을 수 없습니다.")
                # 실패 시 전체 텍스트를 첫 번째 음성으로 처리
                cleaned_text = clean_text_for_tts(text)
                if cleaned_text:
                    return generate_audio_with_openai_tts(cleaned_text, api_key, voice1)
                return None
            
            dialogue_sequence = role_dialogues['sequence']
            
            if not dialogue_sequence:
                st.error(f"⛔ {version_type}에서 대화 순서가 비어있습니다.")
                return None
            
            st.write(f"📋 총 {len(dialogue_sequence)}개의 대화 감지")
            
            # 대화 순서별로 개별 음성 생성
            sentence_audio_files = []
            role_names = {
                'host': voice1, 'guest': voice2, 
                'a': voice1, 'b': voice2
            }
            
            for i, (role, content, order) in enumerate(dialogue_sequence):
                if not content.strip():
                    st.warning(f"⚠️ {i+1}번째 {role.upper()} 대화가 비어있습니다.")
                    continue
                
                voice = role_names.get(role, voice1)
                st.write(f"🎤 {i+1}/{len(dialogue_sequence)} {role.upper()} 음성 생성 중...")
                st.write(f"💭 내용 미리보기: {content[:80]}...")
                
                sentence_audio = generate_audio_with_openai_tts(content, api_key, voice)
                
                if sentence_audio and os.path.exists(sentence_audio):
                    sentence_audio_files.append({
                        'role': role,
                        'content': content,
                        'order': order,
                        'audio_file': sentence_audio,
                        'voice': voice,
                        'index': i
                    })
                    st.write(f"✅ {i+1}. {role.upper()} 음성 생성 완료 ({os.path.getsize(sentence_audio)} bytes)")
                else:
                    st.warning(f"⚠️ {i+1}. {role.upper()} 음성 생성 실패")
            
            if not sentence_audio_files:
                st.error("⛔ 생성된 문장별 음성이 없습니다.")
                return None
            
            st.success(f"🎵 총 {len(sentence_audio_files)}개 문장 음성 생성 완료!")
            
            # 대화 순서대로 오디오 합치기
            st.write("📄 대화 순서에 따라 오디오 합치는 중...")
            
            # 순서대로 정렬 (이미 순서대로 생성되었지만 확실히 하기 위해)
            sentence_audio_files.sort(key=lambda x: x['index'])
            
            # 오디오 파일 경로 리스트 생성
            audio_file_paths = [info['audio_file'] for info in sentence_audio_files]
            
            merged_audio_path = None
            
            # imageio_ffmpeg 우선 시도
            if FFMPEG_AVAILABLE:
                st.write("🔧 imageio_ffmpeg로 오디오 합치기 시도...")
                temp_merged = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
                temp_merged.close()
                
                if merge_audio_files_ffmpeg(audio_file_paths, temp_merged.name):
                    if os.path.exists(temp_merged.name) and os.path.getsize(temp_merged.name) > 0:
                        merged_audio_path = temp_merged.name
                        st.success("🎉 imageio_ffmpeg로 대화 순서 교차 오디오 합성 완료!")
                    else:
                        st.warning("⚠️ imageio_ffmpeg 합성 파일이 비어있습니다.")
            
            # ffmpeg 실패시 pydub 시도
            if not merged_audio_path and PYDUB_AVAILABLE:
                st.write("🔧 pydub로 오디오 합치기 시도...")
                merged_audio_path = merge_audio_files_pydub(audio_file_paths)
                if merged_audio_path:
                    st.success("🎉 pydub로 대화 순서 교차 오디오 합성 완료!")
            
            # 결과 구성
            result = {
                'sentences': sentence_audio_files  # 개별 문장 정보
            }
            
            # 통합 파일이 성공적으로 생성된 경우 추가
            if merged_audio_path:
                result['merged'] = merged_audio_path
            
            # 기존 형식과의 호환성을 위해 역할별 대표 파일도 포함
            role1_key = 'host' if version_type == 'podcast' else 'a'
            role2_key = 'guest' if version_type == 'podcast' else 'b'
            
            # 각 역할의 첫 번째 파일을 대표로 설정
            for audio_info in sentence_audio_files:
                if audio_info['role'] == role1_key and role1_key not in result:
                    result[role1_key] = audio_info['audio_file']
                elif audio_info['role'] == role2_key and role2_key not in result:
                    result[role2_key] = audio_info['audio_file']
            
            return result
        
        # 단일 음성 (원본, 기초, TED)
        st.write(f"🎯 {version_type.upper()} 단일 음성 생성 중...")
        cleaned_text = clean_text_for_tts(text)
        
        if not cleaned_text:
            st.error(f"⛔ 텍스트 정리 후 내용이 없습니다.")
            return None
            
        voice = voice2 if version_type == 'ted' else voice1
        st.write(f"🎤 사용할 음성: {voice}")
        
        return generate_audio_with_openai_tts(cleaned_text, api_key, voice)
        
    except Exception as e:
        st.error(f"음성 생성 중 예외 발생: {str(e)}")
        import traceback
        st.error(f"상세 오류:\n{traceback.format_exc()}")
        return None


def display_audio_with_loop_option(audio_file, label, unique_key):
    """반복재생 옵션이 있는 오디오 플레이어 (모바일 호환성 개선)"""
    if os.path.exists(audio_file):
        # 모바일 감지 (User Agent 기반)
        # Streamlit에서는 직접 User Agent를 가져올 수 없으므로, 
        # 화면 크기나 다른 방법으로 모바일을 감지하거나, 두 가지 옵션을 모두 제공
        
        col1, col2 = st.columns([1, 4])
        
        with col1:
            # 반복재생 체크박스
            loop_enabled = st.checkbox(f"🔁", key=f"loop_{unique_key}", 
                                     value=False, 
                                     help="반복재생 (모바일에서는 지원되지 않을 수 있습니다)")
        
        with col2:
            # 모바일 호환성을 위해 두 가지 방식 모두 제공
            if loop_enabled:
                # 먼저 HTML 방식 시도
                try:
                    with open(audio_file, 'rb') as f:
                        audio_bytes = f.read()
                    
                    # 파일 크기 제한 (모바일 고려)
                    if len(audio_bytes) < 5 * 1024 * 1024:  # 5MB 미만
                        audio_base64 = base64.b64encode(audio_bytes).decode()
                        audio_html = f'''
                        <div style="margin: 10px 0;">
                            <audio controls loop style="width: 100%; max-width: 400px;">
                                <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
                                <p>브라우저에서 오디오를 지원하지 않습니다. 아래 기본 플레이어를 사용하세요.</p>
                            </audio>
                        </div>
                        '''
                        st.markdown(audio_html, unsafe_allow_html=True)
                        
                        # 모바일에서 작동하지 않을 경우를 대비한 대체 플레이어
                        with st.expander("📱 모바일용 대체 플레이어", expanded=False):
                            st.audio(audio_file, format='audio/mp3')
                            st.caption("모바일에서 반복재생이 작동하지 않으면 이 플레이어를 사용하세요")
                    else:
                        # 파일이 너무 크면 기본 플레이어 사용
                        st.audio(audio_file, format='audio/mp3')
                        st.caption("⚠️ 파일이 커서 기본 플레이어를 사용합니다")
                        
                except Exception as e:
                    # HTML 방식 실패 시 기본 플레이어 사용
                    st.audio(audio_file, format='audio/mp3')
                    st.caption("⚠️ 반복재생을 사용할 수 없어 기본 플레이어를 사용합니다")
            else:
                # 일반 재생 모드
                st.audio(audio_file, format='audio/mp3')
    else:
        st.warning("⚠️ 오디오 파일을 찾을 수 없습니다.")


def display_results(results, version):
    """개별 결과 표시 함수 (개선된 Multi-Audio 지원 + 반복재생)"""
    if not results:
        return
        
    version_names = {
        'original': '원본 스크립트',
        'basic': '기초 말하기',
        'ted': 'TED 3분 말하기', 
        'podcast': '팟캐스트 대화',
        'dialog': '일상 대화'
    }
    
    version_name = version_names.get(version, version.upper())
    
    st.markdown(f"## 📋 {version_name} 결과")
    
    script_key = f"{version}_script" if version != 'original' else 'original_script'
    audio_key = f"{version}_audio" if version != 'original' else 'original_audio'
    translation_key = f"{version}_korean_translation"
    
    if script_key in results:
        st.markdown("### 🇺🇸 English Script")
        st.markdown(f'''
        <div style="
            background: linear-gradient(135deg, #f0f2f6, #e8eaf0);
            padding: 1.5rem;
            border-radius: 15px;
            margin: 1rem 0;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        ">
            <div style="
                font-size: 1.1rem;
                line-height: 1.8;
                color: #1f1f1f;
                font-family: 'Georgia', serif;
            ">{results[script_key]}</div>
        </div>
        ''', unsafe_allow_html=True)
        
        # 개선된 오디오 재생 (반복재생 옵션 포함)
        if audio_key in results and results[audio_key]:
            st.markdown("### 🎧 Audio")
            audio_data = results[audio_key]
            
            # 단일 오디오 파일인 경우
            if isinstance(audio_data, str) and os.path.exists(audio_data):
                display_audio_with_loop_option(audio_data, f"{version_name} 메인 오디오", f"main_{version}")
            
            # 개선된 다중 오디오 파일인 경우
            elif isinstance(audio_data, dict):
                # 통합된 대화 오디오 파일이 있으면 먼저 표시
                if 'merged' in audio_data and os.path.exists(audio_data['merged']):
                    st.markdown("**🎵 완전한 대화 순서 음성 (A ↔ B 교차)**")
                    display_audio_with_loop_option(audio_data['merged'], "통합 대화", f"merged_{version}")
                    st.markdown("---")
                
                # 문장별 세부 정보가 있으면 표시
                if 'sentences' in audio_data and isinstance(audio_data['sentences'], list):
                    with st.expander("🔍 문장별 음성 세부사항", expanded=False):
                        sentences = audio_data['sentences']
                        st.write(f"총 {len(sentences)}개 문장으로 구성")
                        
                        for j, sentence_info in enumerate(sentences):
                            role = sentence_info['role'].upper()
                            content_preview = sentence_info['content'][:100] + "..." if len(sentence_info['content']) > 100 else sentence_info['content']
                            voice_used = sentence_info['voice']
                            
                            st.markdown(f"**{j+1}. {role} ({voice_used})**")
                            st.markdown(f"*{content_preview}*")
                            
                            if os.path.exists(sentence_info['audio_file']):
                                display_audio_with_loop_option(
                                    sentence_info['audio_file'], 
                                    f"{role} 문장 {j+1}", 
                                    f"sentence_{version}_{j}"
                                )
                            st.markdown("---")
                
                # 기존 개별 음성들도 표시 (호환성)
                if version == 'podcast':
                    col1, col2 = st.columns(2)
                    with col1:
                        if 'host' in audio_data and os.path.exists(audio_data['host']):
                            st.markdown("**🎤 Host (음성언어-1) 대표**")
                            display_audio_with_loop_option(audio_data['host'], "Host 대표", f"host_{version}")
                    with col2:
                        if 'guest' in audio_data and os.path.exists(audio_data['guest']):
                            st.markdown("**🎙️ Guest (음성언어-2) 대표**")
                            display_audio_with_loop_option(audio_data['guest'], "Guest 대표", f"guest_{version}")
                
                elif version == 'dialog':
                    col1, col2 = st.columns(2)
                    with col1:
                        if 'a' in audio_data and os.path.exists(audio_data['a']):
                            st.markdown("**👤 Person A (음성언어-1) 대표**")
                            display_audio_with_loop_option(audio_data['a'], "Person A 대표", f"a_{version}")
                    with col2:
                        if 'b' in audio_data and os.path.exists(audio_data['b']):
                            st.markdown("**👥 Person B (음성언어-2) 대표**")
                            display_audio_with_loop_option(audio_data['b'], "Person B 대표", f"b_{version}")
            else:
                st.warning("⚠️ 오디오 파일을 찾을 수 없습니다.")
        
        # 한국어 번역 표시
        if version == 'original' and 'korean_translation' in results:
            st.markdown("### 🇰🇷 한국어 번역")
            st.markdown(f'''
            <div style="
                background: linear-gradient(135deg, #f0f2f6, #e8eaf0);
                padding: 1rem;
                border-radius: 10px;
                margin: 1rem 0;
            ">
                <div style="
                    font-size: 0.95rem;
                    color: #666;
                    font-style: italic;
                    line-height: 1.6;
                ">{results["korean_translation"]}</div>
            </div>
            ''', unsafe_allow_html=True)
        
        elif translation_key in results and results[translation_key]:
            st.markdown("### 🇰🇷 한국어 번역")
            st.markdown(f'''
            <div style="
                background: linear-gradient(135deg, #f0f2f6, #e8eaf0);
                padding: 1rem;
                border-radius: 10px;
                margin: 1rem 0;
            ">
                <div style="
                    font-size: 0.95rem;
                    color: #666;
                    font-style: italic;
                    line-height: 1.6;
                ">{results[translation_key]}</div>
            </div>
            ''', unsafe_allow_html=True)


def init_session_state():
    """세션 상태 초기화"""
    defaults = {
        'api_key': '',
        'model': 'gpt-4o-mini',
        'voice1': 'alloy',
        'voice2': 'nova',
        'script_results': {},
        'input_content': '',
        'input_method': 'text',
        'category': '일반',
        'image_description': '',
        'storage': SimpleStorage(),
        'generation_logs': []
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def script_creation_page():
    """스크립트 생성 페이지 (탭별 개별 생성 버전)"""
    st.header("✏️ 스크립트 작성")
    
    st.markdown("### 📝 새 스크립트 만들기")
    
    col1, col2 = st.columns(2)
    
    with col1:
        category = st.selectbox(
            "카테고리 선택",
            ["일반", "비즈니스", "여행", "교육", "건강", "기술", "문화", "스포츠"],
            help="스크립트의 주제를 선택하세요"
        )
    
    with col2:
        # 새 프로젝트 시작 버튼
        if st.button("🆕 새 프로젝트 시작", type="primary"):
            # 현재 프로젝트 정보 초기화
            for key in ['current_project_id', 'current_project_folder']:
                if key in st.session_state:
                    del st.session_state[key]
            # 스크립트 결과 초기화
            st.session_state.script_results = {}
            st.success("새 프로젝트가 시작되었습니다!")
            st.rerun()
    
    # 현재 프로젝트 상태 표시
    if 'current_project_id' in st.session_state:
        st.info(f"📝 현재 프로젝트: {st.session_state.current_project_id} | 같은 폴더에 모든 버전이 저장됩니다")
    else:
        st.info("🆕 새 프로젝트 - 첫 번째 저장 시 새 폴더가 생성됩니다")
    
    input_method = st.radio(
        "입력 방법 선택",
        ["텍스트", "이미지", "파일"],
        horizontal=True
    )
    
    input_content = ""
    image_description = ""
    
    if input_method == "텍스트":
        input_content = st.text_area(
            "주제 또는 내용 입력",
            height=100,
            placeholder="예: 환경 보호의 중요성에 대해 설명하는 스크립트를 만들어주세요."
        )
    
    elif input_method == "이미지":
        uploaded_image = st.file_uploader(
            "이미지 업로드",
            type=['png', 'jpg', 'jpeg'],
            help="이미지를 기반으로 영어 스크립트를 생성합니다"
        )
        
        image_description = st.text_area(
            "이미지 설명 추가",
            height=80,
            placeholder="이미지에 대한 추가 설명이나 생성하고 싶은 스크립트의 방향을 입력하세요 (선택사항)"
        )
        
        if uploaded_image:
            image = Image.open(uploaded_image)
            st.image(image, caption="업로드된 이미지", use_column_width=True)
            input_content = f"이 이미지를 설명하고 관련된 영어 학습 스크립트를 만들어주세요. 추가 설명: {image_description}" if image_description else "이 이미지를 설명하고 관련된 영어 학습 스크립트를 만들어주세요."
    
    else:
        uploaded_file = st.file_uploader(
            "텍스트 파일 업로드",
            type=['txt', 'md'],
            help="텍스트 파일의 내용을 기반으로 스크립트를 생성합니다"
        )
        if uploaded_file:
            input_content = uploaded_file.read().decode('utf-8')
            st.text_area("파일 내용 미리보기", input_content[:500] + "...", height=100, disabled=True)
    
    if not input_content.strip():
        st.warning("내용을 입력해주세요!")
        return
    
    # 세션 상태 업데이트
    st.session_state.input_content = input_content
    st.session_state.input_method = input_method
    st.session_state.category = category
    st.session_state.image_description = image_description
    
    # 탭별 스크립트 생성
    st.markdown("---")
    
    # 탭 생성
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📄 원본 스크립트", 
        "🔤 기초 말하기", 
        "🎯 TED", 
        "🎙️ PODCAST", 
        "💬 DIALOG"
    ])
    
    # 원본 스크립트 탭
    with tab1:
        handle_version_tab('original', '원본 스크립트', input_content)
    
    # 기초 말하기 탭
    with tab2:
        handle_version_tab('basic', '기초 말하기', input_content)
    
    # TED 탭
    with tab3:
        handle_version_tab('ted', 'TED 3분 말하기', input_content)
    
    # 팟캐스트 탭
    with tab4:
        handle_version_tab('podcast', '팟캐스트 대화', input_content)
    
    # 대화 탭
    with tab5:
        handle_version_tab('dialog', '일상 대화', input_content)


def handle_version_tab(version, version_name, input_content):
    """개별 버전 탭 처리"""
    st.markdown(f"### 📝 {version_name}")
    
    # API 키 확인
    if not st.session_state.api_key:
        st.error("먼저 설정에서 API Key를 입력해주세요!")
        return
    
    # 현재 버전의 결과 확인
    current_results = st.session_state.script_results.get(version, {})
    
    col1, col2 = st.columns(2)
    
    with col1:
        # 스크립트 생성 버튼
        if st.button(f"📝 {version_name} 스크립트 작성", key=f"script_{version}"):
            generate_script(version, version_name, input_content)
    
    with col2:
        # 음성 생성 버튼 (스크립트가 있을 때만 활성화)
        script_key = f"{version}_script" if version != 'original' else 'original_script'
        if script_key in current_results:
            if st.button(f"🎵 {version_name} 음성 작성", key=f"audio_{version}"):
                generate_audio(version, version_name, current_results[script_key])
        else:
            st.button(f"🎵 {version_name} 음성 작성", disabled=True, key=f"audio_{version}_disabled")
            st.caption("먼저 스크립트를 생성해주세요")
    
    # 저장 버튼
    if current_results:
        if st.button(f"💾 {version_name} 저장", key=f"save_{version}"):
            save_individual_version(version, current_results)
    
    # 결과 표시
    if current_results:
        display_results(current_results, version)


def generate_script(version, version_name, input_content):
    """개별 스크립트 생성"""
    with st.spinner(f"{version_name} 스크립트 생성 중..."):
        # LLM 프로바이더 초기화
        llm_provider = SimpleLLMProvider(
            st.session_state.api_key,
            st.session_state.model
        )
        
        if not llm_provider.client:
            st.error("LLM 클라이언트 초기화 실패. API 키와 설정을 확인해주세요.")
            return
        
        # 버전별 프롬프트 생성
        prompt = get_version_prompt(version, input_content, st.session_state.category)
        
        # 스크립트 생성
        response = llm_provider.generate_content(prompt)
        
        if response:
            # 제목과 스크립트 분리
            english_title = "Generated Script"
            korean_title = "생성된 스크립트"
            script_content = response
            
            lines = response.split('\n')
            for line in lines:
                if line.startswith('ENGLISH TITLE:'):
                    english_title = line.replace('ENGLISH TITLE:', '').strip()
                elif line.startswith('KOREAN TITLE:'):
                    korean_title = line.replace('KOREAN TITLE:', '').strip()
            
            script_start = response.find('SCRIPT:')
            if script_start != -1:
                script_content = response[script_start+7:].strip()
            
            # 결과 저장
            if version not in st.session_state.script_results:
                st.session_state.script_results[version] = {}
            
            st.session_state.script_results[version]['title'] = english_title
            st.session_state.script_results[version]['korean_title'] = korean_title
            
            script_key = f"{version}_script" if version != 'original' else 'original_script'
            st.session_state.script_results[version][script_key] = script_content
            
            # 한국어 번역 생성
            generate_translation(version, script_content, llm_provider)
            
            st.success(f"✅ {version_name} 스크립트 생성 완료!")
            st.rerun()
        else:
            st.error(f"⌚ {version_name} 스크립트 생성 실패")


def generate_translation(version, script_content, llm_provider):
    """한국어 번역 생성"""
    translation_prompt = f"""
    Translate the following English text to natural, fluent Korean.
    Focus on meaning rather than literal translation.
    Use conversational Korean that sounds natural.
    
    English Text:
    {script_content}
    
    Provide only the Korean translation:
    """
    
    translation = llm_provider.generate_content(translation_prompt)
    if translation:
        translation_key = f"{version}_korean_translation" if version != 'original' else 'korean_translation'
        st.session_state.script_results[version][translation_key] = translation


def generate_audio(version, version_name, script_content):
    """개별 음성 생성"""
    with st.spinner(f"{version_name} 음성 생성 중..."):
        audio = generate_multi_voice_audio(
            script_content,
            st.session_state.api_key,
            st.session_state.voice1,
            st.session_state.voice2,
            version
        )
        
        if audio:
            audio_key = f"{version}_audio" if version != 'original' else 'original_audio'
            st.session_state.script_results[version][audio_key] = audio
            
            if isinstance(audio, dict):
                st.success(f"✅ {version_name} 다중 음성 생성 완료!")
            else:
                st.success(f"✅ {version_name} 음성 생성 완료!")
            st.rerun()
        else:
            st.error(f"⌚ {version_name} 음성 생성 실패")


def save_individual_version(version, results):
    """개별 버전 저장 - 같은 프로젝트 폴더에 누적 저장"""
    storage = st.session_state.storage
    
    # 현재 프로젝트 ID 확인 (세션에 저장된 경우)
    if 'current_project_id' not in st.session_state:
        # 새 프로젝트 생성
        project_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.session_state.current_project_id = project_id
        st.session_state.current_project_folder = None
    else:
        project_id = st.session_state.current_project_id
    
    # 전체 결과에서 현재 버전만 추출해서 저장
    save_results = {}
    
    # 공통 정보
    if 'title' in results:
        save_results['title'] = results['title']
    if 'korean_title' in results:
        save_results['korean_title'] = results['korean_title']
    
    # 버전별 데이터 복사
    for key, value in results.items():
        save_results[key] = value
    
    # 기존 프로젝트가 있는지 확인하고 업데이트
    saved_project_id, project_path = storage.save_or_update_project(
        save_results,
        st.session_state.input_content,
        st.session_state.input_method,
        st.session_state.category,
        project_id,
        st.session_state.current_project_folder
    )
    
    if saved_project_id:
        st.session_state.current_project_folder = project_path
        st.balloons()
        st.success("저장 완료! 연습하기 탭에서 확인하세요.")
        time.sleep(1)
        st.rerun()


def get_version_prompt(version, input_content, category):
    """버전별 프롬프트 생성"""
    base_info = f"""
    Input Type: {st.session_state.input_method.lower()}
    Category: {category}
    Content: {input_content}
    """
    
    if version == 'original':
        return f"""
        Create a natural, engaging English script based on the following input.
        
        {base_info}
        
        Requirements:
        1. Create natural, conversational American English suitable for speaking practice
        2. Use everyday vocabulary and expressions that Americans commonly use
        3. Length: 200-300 words
        4. Include engaging expressions and practical vocabulary
        5. Make it suitable for intermediate English learners
        6. Structure with clear introduction, main content, and conclusion
        7. Include both English and Korean titles
        8. Use casual, friendly tone like Americans speak in daily life
        
        Format your response as:
        ENGLISH TITLE: [Create a clear, descriptive English title]
        KOREAN TITLE: [Create a clear, descriptive Korean title]
        
        SCRIPT:
        [Your natural American English script here]
        """
    
    elif version == 'basic':
        return f"""
        Create a very simple English script for absolute beginners based on the following input.
        
        {base_info}
        
        Requirements:
        1. Use only the most basic English vocabulary (elementary level)
        2. Create exactly 5 sentences
        3. Use simple present tense mostly
        4. Each sentence should be 5-10 words maximum
        5. Use very common, everyday words that beginners know
        6. Make it practical for real-life situations
        7. Include both English and Korean titles
        8. Focus on clear, simple expressions
        
        Example format:
        - "I like apples."
        - "The weather is nice today."
        - "My family is happy."
        
        Format your response as:
        ENGLISH TITLE: [Simple, clear English title]
        KOREAN TITLE: [Simple Korean title]
        
        SCRIPT:
        [Exactly 5 very simple English sentences here]
        """
    
    elif version == 'ted':
        return f"""
        Transform the following into a TED-style 3-minute presentation format.
        
        {base_info}
        
        Requirements:
        1. Add a powerful hook opening
        2. Include personal stories or examples
        3. Create 2-3 main points with clear transitions
        4. End with an inspiring call to action
        5. Use natural American English with TED-style language and pacing
        6. Keep it around 400-450 words (3 minutes speaking)
        7. Add [Opening Hook], [Main Point 1], etc. markers for structure
        8. Use conversational, engaging tone like popular TED speakers
        9. Include both English and Korean titles
        
        Format your response as:
        ENGLISH TITLE: [Inspiring TED-style title]
        KOREAN TITLE: [Korean title]
        
        SCRIPT:
        [Your TED-style presentation script here]
        """
    
    elif version == 'podcast':
        return f"""
        Create a natural 2-person podcast dialogue using everyday American English.
        
        {base_info}
        
        Requirements:
        1. Create natural conversation between Host and Guest
        2. Include follow-up questions and responses
        3. Add conversational fillers and natural expressions that Americans use
        4. Make it informative but casual and friendly
        5. Around 400 words total
        6. Format as "Host: [dialogue]" and "Guest: [dialogue]"
        7. Add [Intro Music Fades Out], [Background ambiance] etc. for atmosphere
        8. Use everyday vocabulary and expressions
        9. Include both English and Korean titles
        
        Format your response as:
        ENGLISH TITLE: [Podcast episode title]
        KOREAN TITLE: [Korean title]
        
        SCRIPT:
        [Your podcast dialogue script here]
        """
    
    elif version == 'dialog':
        return f"""
        Create a practical daily conversation using natural American English.
        
        {base_info}
        
        Requirements:
        1. Create realistic daily situation dialogue between two people
        2. Use common, practical expressions that Americans use in daily life
        3. Include polite phrases and natural responses
        4. Make it useful for real-life situations
        5. Around 300 words
        6. Format as "A: [dialogue]" and "B: [dialogue]"
        7. Add "Setting: [location/situation]" at the beginning
        8. Use casual, friendly American conversational style
        9. Include both English and Korean titles
        
        Format your response as:
        ENGLISH TITLE: [Practical conversation title]
        KOREAN TITLE: [Korean title]
        
        SCRIPT:
        [Your daily conversation script here]
        """
    
    return ""


def practice_page():
    """연습하기 페이지 - 개선된 오디오 구조 지원"""
    st.header("🎯 연습하기")
    
    storage = st.session_state.storage
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("🔄 새로고침"):
            st.rerun()
    
    try:
        projects = storage.load_all_projects()
        
        st.write(f"📊 로드된 프로젝트 수: {len(projects)}")
        
        if not projects:
            st.warning("저장된 프로젝트가 없습니다.")
            st.markdown("**스크립트 생성** 탭에서 새로운 스크립트를 만들어보세요! 🚀")
            return
        
        st.success(f"📚 총 {len(projects)}개의 프로젝트가 저장되어 있습니다.")
        st.markdown("### 📖 연습할 스크립트 선택")
        
        project_options = {}
        for project in projects:
            display_name = f"{project['title']} ({project['category']}) - {project['created_at'][:10]}"
            project_options[display_name] = project['project_id']
        
        selected_project_name = st.selectbox(
            "프로젝트 선택",
            list(project_options.keys()),
            help="연습하고 싶은 프로젝트를 선택하세요"
        )
        
        if selected_project_name:
            project_id = project_options[selected_project_name]
            
            project_content = storage.load_project_content(project_id)
            
            if not project_content:
                st.error(f"프로젝트 {project_id}를 로드할 수 없습니다")
                return
            
            metadata = project_content['metadata']
            
            st.markdown("### 📄 프로젝트 정보")
            info_col1, info_col2, info_col3 = st.columns(3)
            
            with info_col1:
                st.markdown(f"**제목**: {metadata['title']}")
            with info_col2:
                st.markdown(f"**카테고리**: {metadata['category']}")
            with info_col3:
                st.markdown(f"**생성일**: {metadata['created_at'][:10]}")
            
            available_versions = []
            
            if 'original_script' in project_content:
                available_versions.append(('original', '원본 스크립트', project_content['original_script']))
            
            version_names = {
                'basic': '기초 말하기',
                'ted': 'TED 3분 말하기',
                'podcast': '팟캐스트 대화', 
                'dialog': '일상 대화'
            }
            
            for version_type, version_name in version_names.items():
                script_key = f"{version_type}_script"
                if script_key in project_content:
                    available_versions.append((version_type, version_name, project_content[script_key]))
            
            st.write(f"📊 사용 가능한 버전: {len(available_versions)}개")
            
            if available_versions:
                tab_names = [v[1] for v in available_versions]
                tabs = st.tabs(tab_names)
                
                for i, (version_type, version_name, content) in enumerate(available_versions):
                    with tabs[i]:
                        st.markdown(f"### 📃 {version_name}")
                        
                        st.markdown(f'''
                        <div class="script-container">
                            <div class="script-text">{content}</div>
                        </div>
                        ''', unsafe_allow_html=True)
                        
                        practice_col1, practice_col2 = st.columns([2, 1])
                        
                        with practice_col2:
                            st.markdown("### 🎧 음성 연습")
                            
                            audio_key = f"{version_type}_audio"
                            if audio_key in project_content:
                                audio_data = project_content[audio_key]
                                
                                # 단일 오디오 파일인 경우
                                if isinstance(audio_data, str) and os.path.exists(audio_data):
                                    display_audio_with_loop_option(audio_data, f"{version_name} 연습", f"practice_main_{version_type}")
                                
                                # 개선된 다중 오디오 파일인 경우
                                elif isinstance(audio_data, dict):
                                    # 통합된 대화 오디오 파일이 있으면 먼저 표시
                                    if 'merged' in audio_data and os.path.exists(audio_data['merged']):
                                        st.markdown("**🎵 완전한 대화 순서 음성**")
                                        display_audio_with_loop_option(audio_data['merged'], "완전한 대화", f"merged_practice_{version_type}")
                                        st.markdown("*A ↔ B 역할이 실제 대화 순서대로 교차 재생됩니다*")
                                        st.markdown("---")
                                    
                                    # 문장별 세부 연습
                                    if 'sentences' in audio_data and isinstance(audio_data['sentences'], list):
                                        with st.expander("🔍 문장별 세부 연습", expanded=False):
                                            sentences = audio_data['sentences']
                                            st.write(f"총 {len(sentences)}개 문장으로 구성")
                                            
                                            for j, sentence_info in enumerate(sentences):
                                                if isinstance(sentence_info, dict):
                                                    role = sentence_info.get('role', 'unknown').upper()
                                                    voice_used = sentence_info.get('voice', 'unknown')
                                                    content_preview = sentence_info.get('content', '')
                                                    audio_file = sentence_info.get('audio_file', '')
                                                    
                                                    if len(content_preview) > 100:
                                                        content_preview = content_preview[:100] + "..."
                                                    
                                                    st.markdown(f"**{j+1}. {role} ({voice_used})**")
                                                    st.markdown(f"*{content_preview}*")
                                                    
                                                    if audio_file and os.path.exists(audio_file):
                                                        display_audio_with_loop_option(
                                                            audio_file,
                                                            f"{role} 문장 {j+1}",
                                                            f"practice_sentence_{version_type}_{j}"
                                                        )
                                                    else:
                                                        st.warning("⚠️ 음성 파일을 찾을 수 없습니다.")
                                                    st.markdown("---")
                                    
                                    # 기존 개별 음성들도 표시 (역할별 대표 연습용)
                                    if version_type == 'podcast':
                                        practice_col_1, practice_col_2 = st.columns(2)
                                        with practice_col_1:
                                            if 'host' in audio_data and os.path.exists(audio_data['host']):
                                                st.markdown("**🎤 Host 대표 연습**")
                                                display_audio_with_loop_option(audio_data['host'], "Host 대표", f"practice_host_{version_type}")
                                        with practice_col_2:
                                            if 'guest' in audio_data and os.path.exists(audio_data['guest']):
                                                st.markdown("**🎙️ Guest 대표 연습**")
                                                display_audio_with_loop_option(audio_data['guest'], "Guest 대표", f"practice_guest_{version_type}")
                                    
                                    elif version_type == 'dialog':
                                        practice_col_1, practice_col_2 = st.columns(2)
                                        with practice_col_1:
                                            if 'a' in audio_data and os.path.exists(audio_data['a']):
                                                st.markdown("**👤 Person A 대표 연습**")
                                                display_audio_with_loop_option(audio_data['a'], "Person A 대표", f"practice_a_{version_type}")
                                        with practice_col_2:
                                            if 'b' in audio_data and os.path.exists(audio_data['b']):
                                                st.markdown("**👥 Person B 대표 연습**")
                                                display_audio_with_loop_option(audio_data['b'], "Person B 대표", f"practice_b_{version_type}")
                                else:
                                    st.warning("⚠️ 음성 파일을 찾을 수 없습니다.")
                            
                            # 연습 팁
                            with st.expander("💡 연습 팁"):
                                if version_type == 'basic':
                                    st.markdown("""
                                    - 천천히 명확하게 발음하기
                                    - 각 단어를 정확히 발음
                                    - 단순한 문장 구조 익히기
                                    - 매일 반복 연습
                                    - 기초 어휘 암기
                                    """)
                                elif version_type == 'ted':
                                    st.markdown("""
                                    - 자신감 있게 말하기
                                    - 감정을 담아서 표현
                                    - 청중과 아이컨택 상상
                                    - 핵심 메시지에 강조
                                    - 제스처와 함께 연습
                                    """)
                                elif version_type == 'podcast':
                                    st.markdown("""
                                    - 자연스럽고 편안한 톤
                                    - 대화하듯 말하기
                                    - 질문과 답변 구분
                                    - 적절한 속도 유지
                                    - **교차 대화**: A → B → A → B 순서로 연습
                                    """)
                                elif version_type == 'dialog':
                                    st.markdown("""
                                    - 일상적이고 친근한 톤
                                    - 상황에 맞는 감정 표현
                                    - 실제 대화처럼 자연스럽게
                                    - 예의 바른 표현 연습
                                    - **역할 교대**: A, B 역할 번갈아 연습
                                    """)
                                else:
                                    st.markdown("""
                                    - 명확한 발음 연습
                                    - 문장별로 나누어 연습
                                    - 녹음해서 비교하기
                                    - 반복 학습으로 유창성 향상
                                    """)
                        
                        # 한국어 번역 표시
                        translation_key = f"{version_type}_korean_translation"
                        if version_type == 'original' and 'korean_translation' in project_content:
                            st.markdown("### 🇰🇷 한국어 번역")
                            st.markdown(f'''
                            <div class="script-container">
                                <div class="translation-text" style="font-style: italic; color: #666;">{project_content["korean_translation"]}</div>
                            </div>
                            ''', unsafe_allow_html=True)
                        elif translation_key in project_content:
                            st.markdown("### 🇰🇷 한국어 번역")
                            st.markdown(f'''
                            <div class="script-container">
                                <div class="translation-text" style="font-style: italic; color: #666;">{project_content[translation_key]}</div>
                            </div>
                            ''', unsafe_allow_html=True)
                
    except Exception as e:
        st.error(f"연습 페이지 로드 오류: {str(e)}")
        import traceback
        st.error(f"상세 오류:\n{traceback.format_exc()}")


def my_scripts_page():
    """내 스크립트 페이지 (간소화된 버전)"""
    st.header("📚 내 스크립트")
    
    storage = st.session_state.storage
    
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        search_query = st.text_input("🔍 검색", placeholder="제목 또는 내용 검색...")
    
    with col2:
        category_filter = st.selectbox(
            "카테고리",
            ["전체", "일반", "비즈니스", "여행", "교육", "건강", "기술", "문화", "스포츠"]
        )
    
    with col3:
        sort_order = st.selectbox("정렬", ["최신순", "제목순"])
    
    projects = storage.load_all_projects()
    
    if search_query:
        projects = [p for p in projects if search_query.lower() in p['title'].lower()]
    
    if category_filter != "전체":
        projects = [p for p in projects if p['category'] == category_filter]
    
    if sort_order == "제목순":
        projects.sort(key=lambda x: x['title'])
    else:
        projects.sort(key=lambda x: x['created_at'], reverse=True)
    
    if projects:
        st.write(f"총 {len(projects)}개의 프로젝트")
        
        for i in range(0, len(projects), 2):
            cols = st.columns(2)
            
            for j, col in enumerate(cols):
                if i + j < len(projects):
                    project = projects[i + j]
                    
                    with col:
                        with st.container():
                            st.markdown(f"### 📄 {project['title']}")
                            st.markdown(f"**카테고리**: {project['category']}")
                            st.markdown(f"**생성일**: {project['created_at'][:10]}")
                            st.markdown(f"**버전**: {len(project['versions'])}개")
                            
                            button_cols = st.columns(3)
                            
                            with button_cols[0]:
                                if st.button("📖 보기", key=f"view_{project['project_id']}"):
                                    st.session_state[f"show_detail_{project['project_id']}"] = True
                            
                            with button_cols[1]:
                                if st.button("🎯 연습", key=f"practice_{project['project_id']}"):
                                    st.info("연습하기 탭으로 이동해서 해당 프로젝트를 선택하세요.")
                            
                            with button_cols[2]:
                                if st.button("🗑️ 삭제", key=f"delete_{project['project_id']}"):
                                    if st.session_state.get(f"confirm_delete_{project['project_id']}"):
                                        if storage.delete_project(project['project_id']):
                                            st.success("삭제되었습니다!")
                                            st.rerun()
                                    else:
                                        st.session_state[f"confirm_delete_{project['project_id']}"] = True
                                        st.warning("한 번 더 클릭하면 삭제됩니다.")
                            
                            if st.session_state.get(f"show_detail_{project['project_id']}"):
                                with st.expander(f"📋 {project['title']} 상세보기", expanded=True):
                                    project_content = storage.load_project_content(project['project_id'])
                                    
                                    if project_content:
                                        if 'original_script' in project_content:
                                            st.markdown("#### 🇺🇸 영어 스크립트")
                                            st.markdown(project_content['original_script'])
                                        
                                        if 'korean_translation' in project_content:
                                            st.markdown("#### 🇰🇷 한국어 번역")
                                            st.markdown(project_content['korean_translation'])
                                        
                                        st.markdown("#### 📝 연습 버전들")
                                        
                                        version_names = {
                                            'basic': '기초 말하기',
                                            'ted': 'TED 3분 말하기',
                                            'podcast': '팟캐스트 대화',
                                            'dialog': '일상 대화'
                                        }
                                        
                                        for version_type, version_name in version_names.items():
                                            script_key = f"{version_type}_script"
                                            translation_key = f"{version_type}_korean_translation"
                                            
                                            if script_key in project_content:
                                                st.markdown(f"**{version_name}**")
                                                content = project_content[script_key]
                                                preview = content[:200] + "..." if len(content) > 200 else content
                                                st.markdown(preview)
                                                
                                                if translation_key in project_content:
                                                    st.markdown("*한국어 번역:*")
                                                    translation = project_content[translation_key]
                                                    translation_preview = translation[:200] + "..." if len(translation) > 200 else translation
                                                    st.markdown(f"*{translation_preview}*")
                                                
                                                st.markdown("---")
                                    
                                    if st.button("닫기", key=f"close_{project['project_id']}"):
                                        st.session_state[f"show_detail_{project['project_id']}"] = False
                                        st.rerun()
    else:
        st.info("저장된 프로젝트가 없습니다.")
        st.markdown("**스크립트 생성** 탭에서 새로운 프로젝트를 만들어보세요! 🚀")


def settings_page():
    """설정 페이지 (간소화된 버전)"""
    st.header("⚙️ 환경 설정")
    
    # LLM 설정
    with st.expander("🤖 LLM 설정", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**OpenAI 설정**")
            st.info("현재는 OpenAI만 지원됩니다")
        
        with col2:
            models = ['gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo', 'gpt-3.5-turbo']
            model = st.selectbox("Model 선택", models, index=models.index(st.session_state.model))
            st.session_state.model = model
        
        api_key = st.text_input(
            "OpenAI API Key",
            value=st.session_state.api_key,
            type="password",
            help="OpenAI API 키를 입력하세요"
        )
        st.session_state.api_key = api_key
    
    # Multi-Voice TTS 설정
    with st.expander("🎤 Multi-Voice TTS 설정", expanded=True):
        st.markdown("### 🎵 OpenAI TTS 음성 설정")
        st.info("**음성언어-1**: 원본/기초 스크립트, Host/A 역할 \n**음성언어-2**: TED 말하기, Guest/B 역할")
        
        voice_options = {
            'Alloy (중성, 균형잡힌)': 'alloy',
            'Echo (남성, 명확한)': 'echo', 
            'Fable (남성, 영국 억양)': 'fable',
            'Onyx (남성, 깊고 강한)': 'onyx',
            'Nova (여성, 부드러운)': 'nova',
            'Shimmer (여성, 따뜻한)': 'shimmer'
        }
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 🎙️ 음성언어-1")
            st.markdown("*원본/기초 스크립트, Host, Person A*")
            
            # 현재 음성언어-1 설정 확인 및 기본값 처리
            current_voice1 = st.session_state.voice1
            if current_voice1 not in voice_options.values():
                current_voice1 = 'alloy'
                st.session_state.voice1 = 'alloy'
            
            try:
                current_index1 = list(voice_options.values()).index(current_voice1)
            except ValueError:
                current_index1 = 0
                st.session_state.voice1 = 'alloy'
            
            selected_voice1_name = st.selectbox(
                "음성언어-1 선택", 
                list(voice_options.keys()),
                index=current_index1,
                key="voice1_select"
            )
            st.session_state.voice1 = voice_options[selected_voice1_name]
        
        with col2:
            st.markdown("#### 🎤 음성언어-2")
            st.markdown("*TED 말하기, Guest, Person B*")
            
            # 현재 음성언어-2 설정 확인 및 기본값 처리
            current_voice2 = st.session_state.voice2
            if current_voice2 not in voice_options.values():
                current_voice2 = 'nova'
                st.session_state.voice2 = 'nova'
            
            try:
                current_index2 = list(voice_options.values()).index(current_voice2)
            except ValueError:
                current_index2 = 4  # nova가 다섯 번째
                st.session_state.voice2 = 'nova'
            
            selected_voice2_name = st.selectbox(
                "음성언어-2 선택", 
                list(voice_options.keys()),
                index=current_index2,
                key="voice2_select"
            )
            st.session_state.voice2 = voice_options[selected_voice2_name]

        # 음성 적용 규칙 설명
        st.markdown("### 📋 음성 적용 규칙")
        st.markdown("""
        | 스크립트 유형 | 음성 배정 | 설명 |
        |--------------|-----------|------|
        | **원본 스크립트** | 음성언어-1 | 단일 화자 |
        | **기초 말하기** | 음성언어-1 | 단일 화자 (초보자용) |
        | **TED 3분 말하기** | 음성언어-2 | 단일 화자 (프레젠테이션) |
        | **팟캐스트 대화** | Host: 음성언어-1<br>Guest: 음성언어-2 | 2인 대화 |
        | **일상 대화** | Person A: 음성언어-1<br>Person B: 음성언어-2 | 2인 대화 |
        """)
        
        # TTS 테스트
        st.markdown("### 🎵 TTS 테스트")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🎙️ 음성언어-1 테스트"):
                test_text = "Hello, this is voice one testing. I am the host or person A."
                
                if not st.session_state.api_key:
                    st.error("OpenAI API Key가 필요합니다!")
                else:
                    with st.spinner("음성언어-1 테스트 중..."):
                        test_audio = generate_audio_with_openai_tts(
                            test_text,
                            st.session_state.api_key,
                            st.session_state.voice1
                        )
                        if test_audio:
                            st.markdown("**🎤 음성언어-1 테스트 결과:**")
                            display_audio_with_loop_option(test_audio, "음성언어-1 테스트", "test_voice1")
                            st.success("음성언어-1 테스트 완료!")
                        else:
                            st.error("음성언어-1 테스트 실패")
        
        with col2:
            if st.button("🎤 음성언어-2 테스트"):
                test_text = "Hello, this is voice two testing. I am the guest or person B."
                
                if not st.session_state.api_key:
                    st.error("OpenAI API Key가 필요합니다!")
                else:
                    with st.spinner("음성언어-2 테스트 중..."):
                        test_audio = generate_audio_with_openai_tts(
                            test_text,
                            st.session_state.api_key,
                            st.session_state.voice2
                        )
                        if test_audio:
                            st.markdown("**🎵 음성언어-2 테스트 결과:**")
                            display_audio_with_loop_option(test_audio, "음성언어-2 테스트", "test_voice2")
                            st.success("음성언어-2 테스트 완료!")
                        else:
                            st.error("음성언어-2 테스트 실패")
    
    # 시스템 정보
    with st.expander("📊 시스템 정보"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**현재 설정**")
            st.info(f"**모델**: {st.session_state.model}")
            st.info(f"**음성언어-1**: {st.session_state.voice1.title()}")
            st.info(f"**음성언어-2**: {st.session_state.voice2.title()}")
        
        with col2:
            st.markdown("**저장소 정보**")
            storage = st.session_state.storage
            projects = storage.load_all_projects()
            st.info(f"**저장된 프로젝트**: {len(projects)}개")
            st.info(f"**저장 위치**: {storage.base_dir}")
        
        # 오디오 처리 라이브러리 상태
        st.markdown("**오디오 처리 라이브러리 상태**")
        if FFMPEG_AVAILABLE:
            st.success("✅ imageio_ffmpeg 사용 가능 (우선 사용)")
        else:
            st.warning("⚠️ imageio_ffmpeg 없음")
        
        if PYDUB_AVAILABLE:
            st.success("✅ pydub 사용 가능 (fallback)")
        else:
            st.warning("⚠️ pydub 없음")
        
        if not FFMPEG_AVAILABLE and not PYDUB_AVAILABLE:
            st.error("❌ 오디오 합치기 라이브러리가 없습니다. imageio_ffmpeg 또는 pydub를 설치하세요.")
        
        # 모바일 사용 안내
        st.markdown("**📱 모바일 사용자 안내**")
        st.info("""
        **모바일에서 반복재생이 작동하지 않는 경우:**
        - 🔁 체크박스가 보이지 않거나 작동하지 않을 수 있습니다
        - 이는 모바일 브라우저의 오디오 정책 때문입니다
        - '모바일용 대체 플레이어'를 사용하세요
        - 수동으로 반복 재생하여 연습하세요
        """)
        
        # 시스템 테스트
        st.markdown("**시스템 테스트**")
        if st.button("🔧 전체 시스템 테스트"):
            with st.spinner("시스템 테스트 중..."):
                # API 키 테스트
                if st.session_state.api_key:
                    try:
                        llm_provider = SimpleLLMProvider(
                            st.session_state.api_key,
                            st.session_state.model
                        )
                        if llm_provider.client:
                            st.success("✅ OpenAI API 연결 성공")
                        else:
                            st.error("⌛ OpenAI API 연결 실패")
                    except Exception as e:
                        st.error(f"⌛ API 테스트 실패: {str(e)}")
                else:
                    st.warning("⚠️ API 키가 설정되지 않았습니다")
                
                # 저장소 테스트
                try:
                    test_projects = storage.load_all_projects()
                    st.success(f"✅ 저장소 접근 성공 ({len(test_projects)}개 프로젝트)")
                except Exception as e:
                    st.error(f"⌛ 저장소 접근 실패: {str(e)}")


def main():
    """메인 애플리케이션 (탭별 개별 생성 버전 + imageio_ffmpeg 지원)"""
    st.set_page_config(
        page_title="MyTalk - Tab-based Generation with imageio_ffmpeg",
        page_icon="🎙️",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    init_session_state()
    
    # CSS 스타일
    st.markdown("""
    <style>
        .stApp {
            max-width: 100%;
            padding: 1rem;
        }
        .stButton > button {
            width: 100%;
            height: 3rem;
            font-size: 1.1rem;
            margin: 0.5rem 0;
            border-radius: 10px;
        }
        .script-container {
            background: linear-gradient(135deg, #f0f2f6, #e8eaf0);
            padding: 1.5rem;
            border-radius: 15px;
            margin: 1rem 0;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .script-text {
            font-size: 1.1rem;
            line-height: 1.8;
            color: #1f1f1f;
            font-family: 'Georgia', serif;
        }
        .translation-text {
            font-size: 0.95rem;
            color: #666;
            font-style: italic;
            line-height: 1.6;
        }
        .voice-info {
            background: linear-gradient(135deg, #e3f2fd, #f1f8e9);
            padding: 1rem;
            border-radius: 10px;
            margin: 0.5rem 0;
            border-left: 4px solid #2196F3;
        }
        .system-info {
            background: linear-gradient(135deg, #fff3e0, #e8f5e8);
            padding: 0.8rem;
            border-radius: 8px;
            margin: 0.3rem 0;
            border-left: 3px solid #ff9800;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # 헤더
    st.markdown("""
    <div style='text-align: center; padding: 1rem; background: linear-gradient(90deg, #4CAF50, #45a049); border-radius: 10px; margin-bottom: 2rem;'>
        <h1 style='color: white; margin: 0;'>🎙️ MyTalk</h1>
        <p style='color: white; margin: 0; opacity: 0.9;'>Tab-based Script Generation with Multi-Voice TTS (Streamlit Cloud Compatible)</p>
    </div>
    """, unsafe_allow_html=True)
    
    # TTS 엔진 상태 표시
    if st.session_state.api_key:
        st.markdown(f"""
        <div class="voice-info">
            🎵 <strong>Multi-Voice TTS 활성화</strong><br>
            🎙️ <strong>음성언어-1</strong>: {st.session_state.voice1.title()} (원본/기초, Host, A)<br>
            🎤 <strong>음성언어-2</strong>: {st.session_state.voice2.title()} (TED, Guest, B)
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="system-info">
            ⚠️ <strong>API Key 필요</strong> | 설정에서 OpenAI API Key를 입력해주세요
        </div>
        """, unsafe_allow_html=True)
    
    # 네비게이션 탭
    tab1, tab2, tab3, tab4 = st.tabs(["✏️ 스크립트 작성", "🎯 연습하기", "📚 내 스크립트", "⚙️ 설정"])
    
    with tab1:
        script_creation_page()
    
    with tab2:
        practice_page()
    
    with tab3:
        my_scripts_page()
    
    with tab4:
        settings_page()
    
    # 푸터
    st.markdown("---")
    tts_status = f"🎵 Multi-Voice TTS ({st.session_state.voice1}/{st.session_state.voice2})"
    ffmpeg_status = "imageio_ffmpeg" if FFMPEG_AVAILABLE else ("pydub" if PYDUB_AVAILABLE else "No Audio Merger")
    
    st.markdown(f"""
    <div style='text-align: center; color: #666; font-size: 0.8rem; margin-top: 2rem;'>
        <p>MyTalk v3.1 - Tab-based Generation with Multi-Voice TTS (Streamlit Cloud)</p>
        <p>📱 Local Storage | {tts_status} | 🔧 {ffmpeg_status}</p>
        <p>Copyright © 2025 Sunggeun Han (mysomang@gmail.com)</p>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    if not OPENAI_AVAILABLE:
        st.error("OpenAI 라이브러리가 필요합니다.")
        st.code("pip install openai", language="bash")
        st.markdown("### 추가 의존성")
        st.markdown("음성 합치기 기능을 위해 다음 중 하나를 설치하세요:")
        st.code("pip install imageio_ffmpeg  # Streamlit Cloud 추천", language="bash")  
        st.markdown("또는")
        st.code("pip install pydub  # Fallback", language="bash")
        st.stop()
    
    main()