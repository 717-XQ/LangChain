<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <el-icon class="logo-icon"><MagicStick /></el-icon>
        <h1>多工具 AI Agent 助手</h1>
        <p>LangChain + LangGraph · ReAct / 状态图 / 规划执行</p>
      </div>

      <el-tabs v-model="activeTab" class="login-tabs" stretch>
        <!-- 登录 -->
        <el-tab-pane label="登录" name="login">
          <el-form ref="loginFormRef" :model="loginForm" :rules="loginRules" label-position="top" size="large">
            <el-form-item label="用户名" prop="username">
              <el-input v-model="loginForm.username" placeholder="请输入用户名" :prefix-icon="User" clearable />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input v-model="loginForm.password" type="password" placeholder="请输入密码" :prefix-icon="Lock" show-password
                @keyup.enter="handleLogin" />
            </el-form-item>
            <el-button class="submit-btn" type="primary" size="large" :loading="authStore.loading" @click="handleLogin">
              登 录
            </el-button>
          </el-form>
        </el-tab-pane>

        <!-- 注册 -->
        <el-tab-pane label="注册" name="register">
          <el-form ref="registerFormRef" :model="registerForm" :rules="registerRules" label-position="top" size="large">
            <el-form-item label="用户名" prop="username">
              <el-input v-model="registerForm.username" placeholder="3-64字符（字母/数字/下划线/中文）" :prefix-icon="User" clearable />
            </el-form-item>
            <el-form-item label="邮箱" prop="email">
              <el-input v-model="registerForm.email" placeholder="请输入邮箱" :prefix-icon="Message" clearable />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input v-model="registerForm.password" type="password" placeholder="至少6位" :prefix-icon="Lock" show-password />
            </el-form-item>
            <el-form-item label="确认密码" prop="confirmPassword">
              <el-input v-model="registerForm.confirmPassword" type="password" placeholder="再次输入密码" :prefix-icon="Lock" show-password
                @keyup.enter="handleRegister" />
            </el-form-item>
            <el-button class="submit-btn" type="success" size="large" :loading="authStore.loading" @click="handleRegister">
              注 册
            </el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>

      <div class="login-footer">
        <span>技术栈：Vue3 · Vite · Element Plus · Pinia · ECharts · WebSocket</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { User, Lock, Message, MagicStick } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const activeTab = ref<'login' | 'register'>('login')
const loginFormRef = ref<FormInstance>()
const registerFormRef = ref<FormInstance>()

const loginForm = reactive({ username: '', password: '' })
const registerForm = reactive({ username: '', email: '', password: '', confirmPassword: '' })

const loginRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

const registerRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 64, message: '长度3-64字符', trigger: 'blur' }
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== registerForm.password) {
          callback(new Error('两次输入的密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    }
  ]
}

function redirectAfterLogin(): void {
  const redirect = (route.query.redirect as string) || '/'
  router.replace(redirect)
}

async function handleLogin(): Promise<void> {
  if (!loginFormRef.value) return
  await loginFormRef.value.validate()
  try {
    await authStore.login(loginForm.username.trim(), loginForm.password)
    ElMessage.success('登录成功')
    redirectAfterLogin()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '登录失败')
  }
}

async function handleRegister(): Promise<void> {
  if (!registerFormRef.value) return
  await registerFormRef.value.validate()
  try {
    await authStore.register(
      registerForm.username.trim(),
      registerForm.email.trim(),
      registerForm.password
    )
    ElMessage.success('注册成功，已自动登录')
    redirectAfterLogin()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '注册失败')
  }
}
</script>

<style scoped>
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-card {
  width: 420px;
  max-width: 92vw;
  background: #fff;
  border-radius: 16px;
  padding: 36px 40px 24px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
}

.login-header {
  text-align: center;
  margin-bottom: 24px;
}

.logo-icon {
  font-size: 40px;
  color: #667eea;
}

.login-header h1 {
  font-size: 20px;
  color: #303133;
  margin: 8px 0 4px;
}

.login-header p {
  font-size: 12px;
  color: #909399;
  margin: 0;
}

.login-tabs {
  margin-bottom: 8px;
}

.submit-btn {
  width: 100%;
  margin-top: 8px;
  font-weight: 600;
}

.login-footer {
  margin-top: 20px;
  text-align: center;
  font-size: 11px;
  color: #c0c4cc;
}
</style>
