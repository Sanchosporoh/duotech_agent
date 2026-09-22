"""Content identities of local inputs that can change a physical recommendation."""
import hashlib
import json


def fingerprints(root):
    root=root.resolve()
    paths=set((root/'config').glob('*.json'))
    model_folder=root/'runtime/petex_case/IM_2022_06'
    if model_folder.is_dir():
        paths.update(p for p in model_folder.iterdir() if p.suffix.lower() in ('.out','.gap'))
    for name in ('opportunity_register_structured.json','petex_baseline.csv'):
        paths.add(root/'data'/name)
    config=root/'config/diagnostic_models.json'
    if config.exists():
        models=json.loads(config.read_text(encoding='utf-8'))
        for model in models.values():
            for field in ('working_model','prior_curves'):
                if model.get(field):paths.add(root/model[field])
    result={}
    for source in sorted(paths,key=str):
        path=source.resolve()
        if not path.is_relative_to(root):
            raise ValueError('Расчётные зависимости должны находиться в проекте: '+str(source))
        name=path.relative_to(root).as_posix()
        if not path.is_file():
            result[name]='missing'
            continue
        with path.open('rb') as stream:
            result[name]=hashlib.file_digest(stream,'sha256').hexdigest()
    return result
