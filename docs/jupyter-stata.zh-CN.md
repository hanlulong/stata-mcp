# 使用 Jupyter 服务您的 Stata
## 准备
- Stata 17+
- conda
- VScode 或 Jupyter

## 配置基础设施
### Python 环境
我们支持您拥有 conda（anaconda 或 miniconda）环境。

然后在您的终端中运行以下代码（Windows 上使用 PowerShell）
```bash
conda create -n Jupyter-Stata python=3.11
conda activate Jupyter-Stata

# 如果您不确定是否激活了您的环境，可以运行 which python 或 python --version 来确认。
# which python
# python --version

# 安装依赖项
pip install jupyter stata_setup
```

### VScode 配置
创建一个 ".ipynb" 文件，然后选择 Jupyter 内核。
如果您是 macOS 且使用了前面的命令，您可以直接使用以下路径。
```text
/opt/anaconda3/envs/Jupyter-Stata/bin/python
```

```Jupyter
# macOS
import os
os.chdir('/Applications/Stata/utilities') 

from pystata import config
config.init('mp')  # 如果您使用 'stata-se' 请改为 'se'

# Windows
import stata_setup
stata_setup.config("C:/Program Files/Stata17", "mp")
```

然后您可以看到以下窗口：
![pystata-example-window](images/pystata.png)

### Jupyter Lab
如果您更喜欢 Jupyter Lab 而不是 VScode，请使用以下用法。

1. 打开您的 Jupyter Lab
例如：
```bash
conda activate Jupyter-Stata
jupyter lab --notebook-dir="your/project/path"
```

然后您可以在浏览器中看到窗口：
![Jupyter Lab in Brower](images/jupyterlab.png)

您可以直接选择 Notebook-Stata 来使用 Stata 内核，看起来像这样：
![Jupyter Stata Use](images/JupyterLabExample.png)

## 魔法命令（在 Vscode 上，或在 Jupyter lab 中使用 python 内核）
这部分基于[这里](#vscode-config)的结构
```jupyter
%%stata 
## 多行魔法命令

sysuse auto, clear
sum
reg price mpg rep78 trunk weight length
```

```jupyter
%stata scatter mpg price
```

顺便说一句，如果您使用 python 内核，您不仅可以使用 stata，还可以使用 python（pandas）。


## 使用示例（使用 python 内核）
- [示例](examples/jupyter.ipynb) 


## 警告！
您最好不要使用 PyCharm 来写包含 Stata 内容的 Jupyter 文件，因为它会将其识别为 python 代码而不是 Stata。