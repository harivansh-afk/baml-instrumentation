type State = {values: number[]};
export function prepare(raw: string): State { return JSON.parse(raw); }
export async function run(s: State): Promise<string> {
 const a:number[]=[]; for(const v of s.values) a.push(v);
 const lows=[0],highs=[a.length-1];let top=1;
 while(top>0){top--;const lo=lows[top],hi=highs[top];if(lo>=hi)continue;
 const pivot=a[lo+Math.floor((hi-lo)/2)];let lt=lo,i=lo,gt=hi;
 while(i<=gt){if(a[i]<pivot){[a[lt],a[i]]=[a[i],a[lt]];lt++;i++;}else if(a[i]>pivot){[a[gt],a[i]]=[a[i],a[gt]];gt--;}else i++;}
 if(top===lows.length){lows.push(lo);highs.push(lt-1);}else{lows[top]=lo;highs[top]=lt-1;}top++;
 if(top===lows.length){lows.push(gt+1);highs.push(hi);}else{lows[top]=gt+1;highs[top]=hi;}top++;
 }
 return JSON.stringify(a);
}
