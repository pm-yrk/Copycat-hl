'use client'

import { useState } from 'react'
import PublicNav from '../../components/PublicNav'
import PublicMeshBackdrop from '../../components/PublicMeshBackdrop'
import { getSupabase } from '../../lib/supabase'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  async function signIn() {
    try {
      setBusy(true); setMsg('')
      const supabase = await getSupabase()
      const { error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) throw error
      location.href = '/dashboard'
    } catch (e: any) { setMsg(e.message) } finally { setBusy(false) }
  }
  async function signUp() {
    try {
      setBusy(true); setMsg('')
      const supabase = await getSupabase()
      const { error } = await supabase.auth.signUp({ email, password })
      if (error) throw error
      setMsg('Account created. Check your email if confirmation is enabled, then sign in.')
    } catch (e: any) { setMsg(e.message) } finally { setBusy(false) }
  }
  async function resetPassword() {
    try {
      setMsg('')
      if (!email) throw new Error('Enter your email address first.')
      const supabase = await getSupabase()
      const { error } = await supabase.auth.resetPasswordForEmail(email, { redirectTo: location.origin + '/login' })
      if (error) throw error
      setMsg('Password reset email sent.')
    } catch (e: any) { setMsg(e.message) }
  }

  return <div className="public-redesign-root public-login-root">
    <PublicNav/>
    <main className="public-redesign-shell public-login">
      <PublicMeshBackdrop variant="login"/>
      <section className="public-login-layout">
        <div className="public-login-copy">
          <p className="public-eyebrow"><span/> Real-time intelligence</p>
          <h1>50 wallets.<br/>One market view.</h1>
          <p>Live signals, portfolio intelligence and alerts built to make smart-wallet positioning easier to understand.</p>
        </div>

        <section className="public-login-card">
          <div className="public-login-brand"><span>Copy</span><em>cat</em></div>
          <h2>Welcome back.</h2>
          <p>Access your Copycat intelligence dashboard.</p>
          <label>Email<div className="public-input"><span>✉</span><input type="email" autoComplete="email" placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)}/></div></label>
          <label>Password<div className="public-input"><span>▣</span><input type={showPassword ? 'text' : 'password'} autoComplete="current-password" placeholder="Enter your password" value={password} onChange={e => setPassword(e.target.value)}/><button type="button" onClick={() => setShowPassword(v => !v)} aria-label={showPassword ? 'Hide password' : 'Show password'}>{showPassword ? 'Hide' : 'Show'}</button></div></label>
          <div className="public-login-options"><label><input type="checkbox"/> Remember me</label><button type="button" onClick={resetPassword}>Forgot password?</button></div>
          <button className="public-primary full" type="button" disabled={busy} onClick={signIn}>{busy ? 'Signing in…' : 'Sign in'}</button>
          <button className="public-secondary full" type="button" disabled={busy} onClick={signUp}>Create account</button>
          <small className="public-auth-note">◇ Secure authentication powered by Supabase. Copycat never stores your password.</small>
          {msg ? <p className="public-form-msg">{msg}</p> : null}
        </section>
      </section>
    </main>
  </div>
}
