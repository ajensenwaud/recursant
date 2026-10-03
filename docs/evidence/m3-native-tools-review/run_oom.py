import pathlib,subprocess,shlex,os
link=shlex.split(pathlib.Path('/build/CMakeFiles/recursant.dir/link.txt').read_text())
flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if '-fsanitize=address,undefined' in link else []
subprocess.run(['cc','-Wall','-Wextra','-Werror',*flags,'-c','/review/oom.c','-o','/build/oom.o'],check=True)
link[link.index('-o')+1]='recursant-oom'
link += ['/build/oom.o','-Wl,--wrap=json_deep_copy','-Wl,--wrap=json_dumps']
subprocess.run(link,cwd='/build',check=True)
env=dict(os.environ,RECURSANT_BIN='/build/recursant-oom')
subprocess.run(['python3','/review/oom_probe.py'],env=env,check=True)
