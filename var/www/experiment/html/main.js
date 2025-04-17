// 文件上传功能
const selectBtn = document.getElementById('selectBtn');
const fileName = document.getElementById('fileName');
const confirmBtn = document.getElementById('confirmBtn');
let selectedFile = null;

// 选择文件
selectBtn.addEventListener('click', () => {
    console.log('选择文件');
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            selectedFile = e.target.files[0];
            fileName.textContent = selectedFile.name;
            confirmBtn.disabled = false;
        }
    });
    fileInput.click();
});

// 上传文件
confirmBtn.addEventListener('click', () => {
    if (selectedFile) {
        alert(`已上传文件: ${selectedFile.name}`);

        // 1. 判断 Content-Type
        let contentType = 'application/octet-stream';
        const fileName = selectedFile.name.toLowerCase();

        if (fileName.endsWith('.txt')) {
            contentType = 'text/plain';
        } else if (fileName.endsWith('.jpg') || fileName.endsWith('.jpeg')) {
            contentType = 'image/jpeg';
        } else if (fileName.endsWith('.png')) {
            contentType = 'image/png';
        }

        // 2. 读取文件并上传
        const reader = new FileReader();
        reader.onload = (e) => {
            const fileData = e.target.result;

            fetch('/upload', {
                method: 'POST',
                body: fileData,
                headers: {
                    'Content-Type': contentType,
                    'X-Filename': selectedFile.name,
                },
            });
        };
        reader.readAsArrayBuffer(selectedFile);
    }
});

// 登录功能
const usernameInput = document.getElementById('username');
const passwordInput = document.getElementById('password');
const loginBtn = document.getElementById('loginBtn');

// 监听输入框变化，启用或禁用登录按钮
[usernameInput, passwordInput].forEach(input => {
    input.addEventListener('input', () => {
        loginBtn.disabled = !(usernameInput.value && passwordInput.value);
    });
});

// 登录按钮点击事件
loginBtn.addEventListener('click', () => {
    const username = usernameInput.value;
    const password = passwordInput.value;

    const data = `username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`;

    fetch('/login', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: data,
    })
    .then(response => {
        if (response.ok) {
            alert('登录成功！');
            localStorage.setItem('username', username);

            // 登录成功后，启用文件上传按钮
            selectBtn.disabled = false;

            document.querySelector('.login-form').style.display = 'none';
            document.getElementById('welcomeMessage').style.display = 'block';
            document.getElementById('greeting').textContent = `欢迎，${username}！`;
        } else {
            alert('登录失败，请检查用户名和密码！');
        }
    })
    .catch(error => {
        console.error('登录请求失败', error);
        alert('登录请求失败，请稍后再试！');
    });
});

const logoutBtn = document.getElementById('logoutBtn');
logoutBtn.addEventListener('click', () => {
    fetch('/logout', {
        method: 'POST'
    }).then(() => {
        // 清除前端存储
        localStorage.removeItem('username');
        // 恢复页面状态
        document.querySelector('.login-form').style.display = 'block';
        document.getElementById('welcomeMessage').style.display = 'none';
    });
});

// 页面加载自动检测是否登录
window.onload = async function() {
    try {
        const response = await fetch('/check_login');
        const data = await response.json();

        if (data.logged_in) {
            const username = data.username;

            // 登录成功后，启用文件上传按钮
            selectBtn.disabled = false;

            document.querySelector('.login-form').style.display = 'none';
            document.getElementById('welcomeMessage').style.display = 'block';
            document.getElementById('greeting').textContent = `欢迎，${username}！`;
        }

    } catch (error) {
        console.error('Error fetching status:', error);
    }
};


