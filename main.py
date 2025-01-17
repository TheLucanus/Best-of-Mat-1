#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Dependencies
import os
import numpy as np
import pandas as pd
from bom1 import *
import argparse
import difflib
import re
import shutil

import time

import threading
import queue


    
#Counter to show which files are done - previous progress counter will yield results such as (7/24) (1/24) (3/24), which doesnt make a lot of sense to the reader
count = 0

def export(t1, t2, url, outpath, i, args, n, ):
#Convert t1 and t2 to seconds and subtract the prepadding and postpadding.
    t1, t2 = timestamp_to_seconds(t1) - args.prepad, timestamp_to_seconds(t2) + args.postpad
    
    rtrn = ffmpeg_clip(t1,t2,url,outpath, normalize=args.normalizeaudio)

    global count
    count += 1
#    progress = '{n}/{i}'
    if not args.silent:
        if not rtrn:
            #Replace letters causing trouble.
            outpath = outpath.replace(' ','_')\
                                .replace(',','')\
                                .replace("'","") 
            print((str(count)+'/'+str(n)).ljust(9)+ f'{outpath} succesfully exported.')
        else:
            print((str(count)+'/'+str(n)).ljust(9)+ f'{outpath} was not exported.')

#worker threads for queues
def workerThread(q):
    while True:
        args = q.get()[0:]
        # print(args)
        export(*args)
        q.task_done()
        # q.task_done()

def main():
    start_time = time.time()
    
    #Print the welcome message.
    welcome()
    
    #Set up the arguments. 
    parser = argparse.ArgumentParser()
    parser.add_argument('--list', default=False, action='store_true', help='print the list of clips instead of actually exporting them.')
    
    parser.add_argument('--clipname', default=None, type=str,
                        help='specify which clip name you want to export.')
    parser.add_argument('--minrating', default=1, type=int,  choices = range(1,11),
                        help='only export clips with rating >= minrating.')
    parser.add_argument('--maxrating', default=10, type=int, choices = range(1,11),
                        help= 'only export clips with rating <= maxrating.') #Why anyone ever would use this, I don't know.
    parser.add_argument('--minduration', default=0, type=int,
                        help= 'only export clips with duration >= minduration. duration is in seconds.')
    parser.add_argument('--maxduration', default=np.inf, type=int,
                        help='only export clips with duration <= maxduration. duration is in seconds.')
    parser.add_argument('--tag', default='', type=str,
                        help='regex for specfiying which tag you want to export.')
    
    parser.add_argument('--mint1', default=0, type=int, 
                        help='only export clips with mint1 <= t1.')
    parser.add_argument('--maxt1', default=np.inf, type=int,
                        help='only export clips with t1 <= maxt1.')
    parser.add_argument('--mint2', default=0, type=int,
                        help='only export clips with mint2 <= t2.')
    parser.add_argument('--maxt2', default=np.inf, type=int,
                        help='only export clips with t2 <= maxt2.')
    
    parser.add_argument('--prepad', default=0, type=float, help='pads the start of the clip with <prepad> seconds.')
    parser.add_argument('--postpad', default=0, type=float, help='pads the end of clip with <endpad> seconds.')
    
    parser.add_argument('--filetype', default='mp3', type=str, choices=['mp3', 'mp4', 'gif', 'wav'], help='filetype to export as either mp3, mp4 or gif.')
    parser.add_argument('--normalizeaudio', default=True, action='store_true', help='normalize the audio of the output clip. this only works with mp4 at the moment.')
    parser.add_argument('--noprefix', default=False,  action='store_true', help='include prefix specifying info about the clip.')
    parser.add_argument('--clearexport', default=False, action='store_true', help='clear the export folder before exporting.')
    parser.add_argument('--silent', default=False, action='store_true', help='if --silent is passed, then progress is not printed to the console.')
    parser.add_argument('--loadempty', default=False, action='store_true', help='if --loadempty is passed, then csvs located in the "empty" csv folder are also loaded.')
    parser.add_argument('--includeplaceholder', default=False, action='store_true', help='if --loadempty is passed, then placeholders are included.')
    parser.add_argument('--threads', default=4, type=int, help='Amount of threads used to download clips, default 4')
    #TODO: Add some more arguments. 

    args = parser.parse_args()
    
    #A few assertions
    assert args.prepad >= 0, f'args.prepad should be 0 or greater. args.prepad: {args.prepad}'
    assert args.postpad >= 0, f'args.postpad should be 0 or greater. args.postpad: {args.postpad}'
    
    #Load the clips
    clips = load_clips(load_empty = args.loadempty)
    
    n = len(clips)
    
    #Make sure that we have the ./export folder.
    if not os.path.exists('./export'):
        os.mkdir('./export')
    
    #Construct the masks for each query.
    if args.clipname is not None:
        clipname_mask = (clips['name'] == args.clipname).to_numpy()
    else:
        clipname_mask = np.ones(n).astype(bool)
        
    if args.minrating != 1:
        minrating_mask = (args.minrating <= clips['rating']).to_numpy()
    else:
        minrating_mask = np.ones(n).astype(bool)

    if args.maxrating != 10:
        maxrating_mask = (clips['rating'] <= args.maxrating).to_numpy()
    else:
        maxrating_mask = np.ones(n).astype(bool)
        
    if args.minduration != 0:
        minduration_mask = (args.minduration <= clips['duration']).to_numpy()
    else:
        minduration_mask = np.ones(n).astype(bool)
        
    if args.maxduration != np.inf:
        maxduration_mask = (clips['duration'] <= args.maxduration).to_numpy()
    else:
        maxduration_mask = np.ones(n).astype(bool)
    
    if args.tag != '':
        tags = [tag for tag in clips['tag'].unique() if re.search(args.tag, tag) is not None]
        tags_mask = (clips['tag'].isin(tags)).to_numpy()
    else:
        tags_mask = np.ones(n).astype(bool)
        
    if args.mint1 != 0:
        mint1_mask = args.mint1 <= clips['t1'].apply(lambda x : timestamp_to_seconds(x)).to_numpy()
    else:
        mint1_mask = np.ones(n).astype(bool)
        
    if args.maxt1 != np.inf:
        maxt1_mask = clips['t1'].apply(lambda x : timestamp_to_seconds(x)).to_numpy() <= args.maxt1
    else:
        maxt1_mask = np.ones(n).astype(bool)
        
    if args.mint2 != 0:
        mint2_mask = args.mint2 <= clips['t2'].apply(lambda x : timestamp_to_seconds(x)).to_numpy()
    else:
        mint2_mask = np.ones(n).astype(bool)
        
    if args.maxt2 != np.inf:
        maxt2_mask = clips['t2'].apply(lambda x : timestamp_to_seconds(x)).to_numpy() <= args.maxt2
    else:
        maxt2_mask = np.ones(n).astype(bool)
    
    if args.includeplaceholder:
        #We should include placeholders.
        placeholder_mask = np.ones(n).astype(bool)
    else:
        #Only keep clips where the name is not "placeholder".
        placeholder_mask = clips['name'].str.lower() != 'placeholder'
    
    
    if args.noprefix:
        prefix = ''
    else:
        prefix = clips['tag']+'_C'+clips['nclip'].astype(str).str.zfill(2)+'_R'+clips['rating'].astype(str).str.zfill(2)+'_'
    
    
    if args.clearexport:
        if os.path.exists('./export'):
            shutil.rmtree('./export')
        os.mkdir('./export')
        

    #Stitch together the outpath.
    clips['outpath'] = ('./export/'+prefix+clips['name']+'.'+args.filetype).str.replace(' ','_')\
                                                                               .replace(',','')\
                                                                               .replace("'","") 
    
    #Combine all of the masks into a final single mask, and cut out the relevant clips.
    final_mask = (clipname_mask) & (minrating_mask) & (maxrating_mask) & (minduration_mask) & (maxduration_mask) & (tags_mask)\
                 & (mint1_mask) & (maxt1_mask) & (mint2_mask) & (maxt2_mask) & (placeholder_mask)
    
    clips_final = clips.copy().loc[final_mask]
    
    #Check if there are any clips.
    if len(clips_final) == 0:
        if not np.any(clipname_mask):
            print('There are no clips with the specified name.')
            close_match = difflib.get_close_matches(args.clipname, list(clips['name']))
            if close_match != []:
                print(f'Did you perhaps mean {close_match}?')
        else:
            print('No clips met the specified query.')
        return
    
    if args.list:
        print_clips(clips_final)
        if len(clips_final) > 1:
            print('')
            print(f'A total of {len(clips_final)} clips met your criteria.')
        return
    else:
        n = len(clips_final)
        if n > 1:
            input(f'A total of {n} clips were found. Press enter to export. ') #Ask for confirmation if several clips are exported.
            print('')
        
        q = queue.Queue(0)
        num_threads = args.threads if args.threads > 0 else 1

        for t1, t2, url, outpath, i in zip(clips_final['t1'], clips_final['t2'], clips_final['link'], clips_final['outpath'], range(0, n)):
            q.put((t1,t2,url,outpath,i, args, n,))
        for _ in range(num_threads):
            worker = threading.Thread(target=workerThread, args=(q,))
            worker.setDaemon(True)
            worker.start()
        
        q.join()
        # #start threads
        # for thread in t:
        #     thread.start()
        
        # for thread in t:
        #     thread.join()
        
        end_time = time.time()
        print('')
        print("Time elapsed: {:.2f} seconds.".format(end_time-start_time))
        return
                
if __name__ == '__main__':
    main()