"""저장소 전체 Python/JSON/셸 문법과 문서의 로컬 파일 링크 검사 (서비스 호출 없음)."""
import ast,json,re,subprocess,sys
from pathlib import Path
from urllib.parse import unquote,urlsplit
ROOT=Path(__file__).resolve().parents[2]


def check(root=ROOT):
    if (root/'.git').exists():
        proc=subprocess.run(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=root,capture_output=True,check=True)
        paths=[Path(p) for p in proc.stdout.decode().split('\0') if p]
    else:
        # GitHub ZIP / git archive로 받은 학습 자료도 Git 설치·메타데이터 없이 검사한다.
        ignored={'.git','.terraform','.venv','__pycache__','.pytest_cache','build','htmlcov'}
        paths=[p.relative_to(root) for p in root.rglob('*') if p.is_file()
               and not ignored.intersection(p.relative_to(root).parts)
               and not (p.name.endswith('.tfvars') and p.name!='example.tfvars')
               and not any(x in p.name for x in ('.tfstate','.tfplan')) and p.name!='tfplan']
    errors=[];counts={'python':0,'json':0,'shell':0,'local_links':0,'sql_files':0,'terraform_files':0}
    for rel in sorted(set(paths)):
        file=root/rel
        if not file.is_file():continue
        try:
            if file.suffix=='.py':ast.parse(file.read_text(encoding='utf-8'),filename=str(rel));counts['python']+=1
            elif file.suffix=='.json':json.loads(file.read_text(encoding='utf-8'));counts['json']+=1
            elif file.suffix=='.sh' or file.name.endswith('.sh.tftpl'):
                result=subprocess.run(['bash','-n',str(file)],capture_output=True,text=True)
                if result.returncode:errors.append(f'{rel}: {result.stderr.strip()}')
                counts['shell']+=1
            elif file.suffix=='.sql':counts['sql_files']+=1  # 목록만: MySQL 실행 문법 검증은 아니다
            elif file.suffix=='.tf':counts['terraform_files']+=1  # validate.sh에서 별도 검사
            if file.suffix=='.md':
                text=re.sub(r'```.*?```','',file.read_text(encoding='utf-8'),flags=re.S)
                for link in re.findall(r'\]\(([^)]+)\)',text):
                    link=link.strip().strip('<>')
                    if not link or link.startswith('#') or urlsplit(link).scheme:continue
                    target=unquote(urlsplit(link).path)
                    if not target or ' ' in target:continue
                    counts['local_links']+=1
                    if not (file.parent/target).exists():errors.append(f'{rel}: 없는 링크 {target}')
        except (SyntaxError,UnicodeError,json.JSONDecodeError) as exc:errors.append(f'{rel}: {type(exc).__name__} ({exc})')
    return counts,errors


if __name__=='__main__':
    counts,errors=check()
    print(json.dumps({'counts':counts,'errors':errors},ensure_ascii=False,indent=2));sys.exit(bool(errors))
