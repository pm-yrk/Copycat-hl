'use client'

import { FormEvent, useEffect, useState } from 'react'
import PublicNav from '../../components/PublicNav'
import PublicMeshBackdrop from '../../components/PublicMeshBackdrop'
import { getSupabase } from '../../lib/supabase'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [recoveryMode, setRecoveryMode] = useState(false)

  useEffect(() => {
    let mounted = true
    let unsubscribe: (() => void) | undefined
    getSupabase().then((supabase) => {
      const listener = supabase.auth.onAuthStateChange((event) => {
        if (mounted && event === 'PASSWORD_RECOVERY') setRecoveryMode(true)
      })
      unsubscribe = () => listener.data.subscription.unsubscribe()
      if (mounted && (location.hash.includes('type=recovery') || location.search.includes('recovery=1'))) setRecoveryMode(true)
    }).catch(() => {})
    return () => { mounted = false; unsubscribe?.() }
  }, [])

  function validateCredentials() {
    if (!email.trim()) throw new Error('Enter your email address.')
    if (password.length < 6) throw new Error('Password must be at least 6 characters.')
  }

  async function signIn() {
    try {
      setBusy(true); setMsg('')
      validateCredentials()
      const supabase = await getSupabase()
      const { error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) throw error
      location.href = '/dashboard'
    } catch (e: any) { setMsg(e.message) } finally { setBusy(false) }
  }
  async function signUp() {
    try {
      setBusy(true); setMsg('')
      validateCredentials()
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
      const { error } = await supabase.auth.resetPasswordForEmail(email, { redirectTo: location.origin + '/login?recovery=1' })
      if (error) throw error
      setMsg('Password reset email sent.')
    } catch (e: any) { setMsg(e.message) }
  }
  async function updatePassword() {
    try {
      setBusy(true); setMsg('')
      if (password.length < 6) throw new Error('Password must be at least 6 characters.')
      const supabase = await getSupabase()
      const { error } = await supabase.auth.updateUser({ password })
      if (error) throw error
      setRecoveryMode(false)
      setPassword('')
      setMsg('Password updated. You can now sign in.')
      history.replaceState({}, '', '/login')
    } catch (e: any) { setMsg(e.message) } finally { setBusy(false) }
  }
  function submit(event: FormEvent) {
    event.preventDefault()
    if (recoveryMode) updatePassword()
    else signIn()
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

        <form className="public-login-card" onSubmit={submit}>
          <div className="public-login-brand"><span>Copy</span><em>cat</em></div>
          <h2>{recoveryMode ? 'Choose a new password.' : 'Welcome back.'}</h2>
          <p>{recoveryMode ? 'Enter the new password you want to use for Copycat.' : 'Access your Copycat intelligence dashboard.'}</p>
          {!recoveryMode ? <label>Email<div className="public-input"><span>✉</span><input type="email" autoComplete="email" placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)}/></div></label> : null}
          <label>{recoveryMode ? 'New password' : 'Password'}<div className="public-input"><span>▣</span><input type={showPassword ? 'text' : 'password'} autoComplete={recoveryMode ? 'new-password' : 'current-password'} placeholder={recoveryMode ? 'At least 6 characters' : 'Enter your password'} value={password} onChange={e => setPassword(e.target.value)}/><button type="button" onClick={() => setShowPassword(v => !v)} aria-label={showPassword ? 'Hide password' : 'Show password'}>{showPassword ? 'Hide' : 'Show'}</button></div></label>
          {!recoveryMode ? <div className="public-login-options"><span/><button type="button" onClick={resetPassword}>Forgot password?</button></div> : null}
          <button className="public-primary full" type="submit" disabled={busy}>{busy ? 'Please wait…' : recoveryMode ? 'Update password' : 'Sign in'}</button>
          {!recoveryMode ? <button className="public-secondary full" type="button" disabled={busy} onClick={signUp}>Create account</button> : null}
          <small className="public-auth-note">◇ Secure authentication powered by Supabase. Copycat never stores your password.</small>
          {msg ? <p className="public-form-msg">{msg}</p> : null}
        </form>
      </section>
    </main>
  </div>
}
