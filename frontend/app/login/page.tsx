"use client"
import { useState } from 'react'
import Nav from '../../components/Nav'
import LineBackdrop from '../../components/LineBackdrop'
import { getSupabase } from '../../lib/supabase'

export default function Login() {
  const [email,setEmail]=useState('')
  const [password,setPassword]=useState('')
  const [msg,setMsg]=useState('')
  async function signIn(){try{setMsg(''); const supabase=await getSupabase(); const { error }=await supabase.auth.signInWithPassword({email,password}); if(error)throw error; location.href='/dashboard'}catch(e:any){setMsg(e.message)}}
  async function signUp(){try{setMsg(''); const supabase=await getSupabase(); const { error }=await supabase.auth.signUp({email,password}); if(error)throw error; setMsg('Account created. Check your email if confirmation is enabled, then log in.')}catch(e:any){setMsg(e.message)}}
  async function resetPassword(){try{setMsg(''); const supabase=await getSupabase(); const { error }=await supabase.auth.resetPasswordForEmail(email, { redirectTo: location.origin + '/login' }); if(error)throw error; setMsg('Password reset email sent.')}catch(e:any){setMsg(e.message)}}
  return <><Nav/><main className="page-shell login-shell"><LineBackdrop variant="login"/><section className="login-layout"><div className="login-copy"><p className="eyebrow">Members only</p><h1>Welcome back.</h1><p>Log in to view live smart-wallet signals, allocation targets, market-flow pressure, alerts, and API access.</p><div className="login-features"><div><i className="feature-icon signal"/><b>Live signals</b><span>Real-time smart-wallet activity</span></div><div><i className="feature-icon pie"/><b>Portfolio intelligence</b><span>Track positioning bias and exposure</span></div><div><i className="feature-icon flow"/><b>API + alerts</b><span>Data access and 15-minute digests</span></div></div><p className="secure-note">♢ Secure login through Supabase. Copycat never stores your password.</p></div><div className="login-card"><h2>Login</h2><p>Access your Copycat dashboard</p><label>Email<div className="input-wrap"><span>✉</span><input placeholder="you@example.com" value={email} onChange={e=>setEmail(e.target.value)}/></div></label><label>Password<div className="input-wrap"><span>▣</span><input type="password" placeholder="Enter your password" value={password} onChange={e=>setPassword(e.target.value)}/><em>◉</em></div></label><div className="form-row"><label className="check"><input type="checkbox"/> Remember me</label><button className="link-button" onClick={resetPassword} type="button">Forgot password?</button></div><button className="primary-btn full" onClick={signIn}>Login</button><button className="outline-btn full" onClick={signUp}>Create account</button><small>♢ Dashboard access, alerts, and API permissions will be controlled by your subscription.</small>{msg&&<p className="form-msg">{msg}</p>}</div></section></main></>
}
