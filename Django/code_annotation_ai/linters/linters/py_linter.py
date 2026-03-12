# import ast, json, subprocess

# from pathlib import Path

# def check_python_syntax(file_path):
#     try:
#         with open(file_path, "r") as f:
#             source = f.read()
        
#         # Attempt parsing
#         ast.parse(source)
#         return None

#     except SyntaxError as e:
#         # Clean the code: remove tabs and newlines, normalize spaces
#         annotation = {
#             "file": e.filename,
#             "line": e.lineno,
#             "type": e.msg,
#             "original_code": source,
#             "suggested_fix": None,
#             "explanation": []
#         }

#         return annotation
    
# def flake_checker(file_path):
#     cmd = ["flake8", file_path, "--format=json"]
#     result = subprocess.run(cmd, capture_output=True, text=True)

#     return json.loads(result.stdout)

# def folder_loop(folder_path: Path):
#     folder_error_list = []
    
#     for file in folder_path.iterdir():
#         if not file.is_dir():
#             if file.suffix == ".py":
#                 tmpsyntax = check_python_syntax(file)
#                 tmpflake = flake_checker(file)
                
#                 file_string = str(file)
                
#                 to_ai = {
#                     "file": file_string,
#                     "syntax":tmpsyntax,
#                     "flake": tmpflake
#                     }
                                
#                 folder_error_list.append(to_ai)
                
#     return folder_error_list
                
    
# test_folder_res = folder_loop(Path("C:\\School\\be_pro\\ai_code_annotation\\Django\\code_annotation_ai\\test_python_files\\"))
