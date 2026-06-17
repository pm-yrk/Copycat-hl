'use client'
import { useState } from 'react'
import Nav from '../../components/Nav'
import { getSupabase } from '../../lib/supabase'

export default function Login(){
  const [email,setEmail]=useState(''); const [password,setPassword]=useState(''); const [msg,setMsg]=useState('')
  async function signIn(){ const supabase=await getSupabase(); const {error}=await supabase.auth.signInWithPassword({email,password}); if(error)setMsg(error.message); else window.location.href='/dashboard' }
  async function signUp(){ const supabase=await getSupabase(); const {error}=await supabase.auth.signUp({email,password}); if(error)setMsg(error.message); else setMsg('Check your email to confirm your account.') }
  return <><Nav/><main className="container"><div className="auth-shell"><div className="auth-copy"><p className="eyebrow">Members only</p><h1>Welcome back.</h1><p className="muted">Log in to view live smart-wallet signals, allocation targets, and market-flow pressure.</p></div><div className="form card auth-card"><h2>Login</h2><input className="input" placeholder="Email" value={email} onChange={e=>setEmail(e.target.value)}/><input className="input" type="password" placeholder="Password" value={password} onChange={e=>setPassword(e.target.value)}/><div className="links"><button className="btn" onClick={signIn}>Login</button><button className="btn secondary" onClick={signUp}>Create account</button></div>{msg&&<p className="muted form-msg">{msg}</p>}</div></div></main></>
}
