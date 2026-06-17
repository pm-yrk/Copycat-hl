'use client'
import { useState } from 'react'
import Nav from '../../components/Nav'
import { supabase } from '../../lib/supabase'

export default function Login(){
  const [email,setEmail]=useState(''); const [password,setPassword]=useState(''); const [msg,setMsg]=useState('')
  async function signIn(){ const {error}=await supabase.auth.signInWithPassword({email,password}); if(error)setMsg(error.message); else window.location.href='/dashboard' }
  async function signUp(){ const {error}=await supabase.auth.signUp({email,password}); if(error)setMsg(error.message); else setMsg('Check your email to confirm your account.') }
  return <><Nav/><main className="container"><div className="form card"><h1>Login</h1><input className="input" placeholder="Email" value={email} onChange={e=>setEmail(e.target.value)}/><input className="input" type="password" placeholder="Password" value={password} onChange={e=>setPassword(e.target.value)}/><div className="links"><button className="btn" onClick={signIn}>Login</button><button className="btn secondary" onClick={signUp}>Create account</button></div>{msg&&<p className="muted">{msg}</p>}</div></main></>
}
