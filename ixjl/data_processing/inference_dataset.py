import os
import numpy as np
import torch
import torch.utils.data
import random
from collections import defaultdict
from scipy.sparse import coo_matrix
import pickle 
from ops.sparse_ops import array_to_coo

class Inference_Dataset(torch.utils.data.Dataset):
    def __init__(self,data_path,   
                transform=None,
                stride=20,
                window_height= 224,
                window_width = 224,
                max_cutoff=None,
                fill_diagonal_zero=False,
                bounding=200,
                locus_embedding=False,
                task=1):
        """
        #data_path: the path of the input data
        #transform: the transform applied to the input data
        #stride: the stride of the sliding window
        #window_height: the height of the sliding window
        #window_width: the width of the sliding window
        #max_cutoff: the maximum number of valid pixels in a window
        #fill_diagonal_zero: whether to fill the diagonal with zeros
        #bounding: the bounding of scanning region
        """
        self.data_path = data_path
        self.transform = transform
        self.stride = stride
        self.window_height = window_height
        self.window_width = window_width
        self.data = pickle.load(open(data_path,'rb'))
        self.max_cutoff = max_cutoff
        self.fill_diagonal_zero = fill_diagonal_zero
        self.bounding = bounding
        self.locus_embedding = locus_embedding
        self.total_count = 0
        self.input_index = []
        self.dataset_shape = {}
        new_data = {}
        self.task = task
        half_window_width = self.window_width//2
        half_window_height = self.window_height//2
        #revise the data to make it to be symmetrical
        for chrom in self.data:
            hic_data = self.data[chrom]
            #if smaller than half window height, skip
            if hic_data.shape[0]<half_window_height:
                continue
            self.total_count += np.sum(hic_data.data)   
            if hic_data.shape[0]==hic_data.shape[1]:
                combine_row = np.concatenate([hic_data.row,hic_data.col])
                combine_col = np.concatenate([hic_data.col,hic_data.row])
                combine_data = np.concatenate([hic_data.data,hic_data.data])
                hic_data.row = combine_row
                hic_data.col = combine_col
                hic_data.data = combine_data #triu part
                #divide to half for the diagonal region
                select_index= (hic_data.row==hic_data.col)
                hic_data.data[select_index] = hic_data.data[select_index]/2
            input_row_size= max(hic_data.shape[0],self.window_height) #do padding if necessary
            input_col_size= max(hic_data.shape[1],self.window_width)
            if self.task == 5: # schic enhancement
                input_row_size = hic_data.shape[0]
                input_col_size = hic_data.shape[1]
            final_hic_data= coo_matrix((hic_data.data,(hic_data.row,hic_data.col)),
                                       shape=(input_row_size,input_col_size))

            new_data[chrom] = final_hic_data
            self.dataset_shape[chrom] = final_hic_data.shape
            row_size = final_hic_data.shape[0]
            col_size = final_hic_data.shape[1]
            if self.task == 5: # schic enhancement, for padding around the center matrix
                current_array = final_hic_data.toarray()
                if row_size < self.window_height or col_size < self.window_width: # do padding
                    left_up_pad_size = (self.window_height - row_size) // 2
                    right_down_pad_size = self.window_height - row_size - left_up_pad_size
                    final_array = np.pad(current_array,((left_up_pad_size ,right_down_pad_size),(left_up_pad_size ,right_down_pad_size)),'constant',constant_values=(0,0))
                    final_hic_data_padded = array_to_coo(final_array)
                    new_data[chrom] = final_hic_data_padded # update the data
                    row_size = final_hic_data_padded.shape[0] # update the row size
                    col_size = final_hic_data_padded.shape[1] # update the col size
                    
            if self.locus_embedding:
                #raw submatrix extracted from the original matrix
                row_iter_list = list(range(0,row_size-self.window_height,stride))+[row_size-self.window_height]+[row_size-self.window_height-stride]
                for i in row_iter_list:
                    i = max(0,i)
                    row_max_bound = min(row_size,i+self.window_height)
                    
                    
                    #also track of the middle point for better visualization
                    #here it is not wrong, we specifically use the middle point of the diagonal line as the center of current prediction
                    middle_col_point = i+half_window_height
                    col_start = middle_col_point-half_window_width
                    col_max_bound = min(col_size,middle_col_point+half_window_width)
                    col_start = max(0,col_start)
                    self.input_index.append((chrom,i,col_start,row_max_bound,col_max_bound,middle_col_point))
            elif self.task!=6:
                #all inference tasks
                row_iter_list = list(range(0,row_size-self.window_height,stride))+[row_size-self.window_height]+[row_size-self.window_height-stride]
                col_iter_list = list(range(0,col_size-self.window_width,stride))+[col_size-self.window_width]+[col_size-self.window_width-stride]
                for i in row_iter_list:
                    for j in col_iter_list:
                        
                        if abs(i-j)>bounding:
                            continue
                        i = max(0,i)
                        j = max(0,j)
                        row_max_bound = min(i+self.window_height,row_size)
                        col_max_bound = min(j+self.window_width,col_size)
                        middle_col_point = (j+col_max_bound)//2
                        self.input_index.append((chrom,i,j,row_max_bound,col_max_bound,middle_col_point))
            
            else:
                #only for the embedding infer task
                half_window_height = self.window_height//2
                half_window_width = self.window_width//2
                for i in range(0,row_size,stride):
                    for j in range(0,col_size,stride):
                        if abs(i-j)>bounding:
                            continue
                        cur_row = max(0,i-half_window_height)
                        cur_row_end = min(row_size,i+half_window_height)
                        cur_col = max(0,j-half_window_width)
                        cur_col_end = min(col_size,j+half_window_width)
                        middle_col_point = (cur_col+cur_col_end)//2
                        self.input_index.append((chrom,i,j,cur_row_end,
                                                 cur_col_end,middle_col_point))
                

        self.data = new_data
        print("Total reads of input hic: ",self.total_count)
        print("Total number of input windows: ",len(self.input_index))
    def __len__(self):
        return len(self.input_index)
    
    def convert_rgb(self,data_log,max_value):
        data_red = np.ones(data_log.shape)
        data_log1 = (max_value-data_log)/max_value
        data_rgb = np.concatenate([data_red,data_log1,data_log1],axis=0,dtype=np.float32)
        data_rgb = data_rgb.transpose(1,2,0)
        return data_rgb
    
    def __getitem__(self, idx):
        current_index = self.input_index[idx]
        chrom,row_start,col_start,row_end,col_end,col_middle_point = current_index
        row_record_start = row_start
        col_record_start = col_start #this is specifically kept for embedding infer, which returns the center loc as final location for recording.
        current_array = self.data[chrom]

        submat = np.zeros([1,self.window_height,self.window_width])
        if self.task==6:
            row_start = max(0,row_record_start-self.window_height//2)
            col_start = max(0,col_record_start-self.window_width//2)
        #it is a scipy sparse coo matrix
        select_index1 = (current_array.row>=row_start) & (current_array.row<row_end)
        select_index2 = (current_array.col>=col_start) & (current_array.col<col_end)

        final_row = current_array.row[select_index1&select_index2]
        final_col = current_array.col[select_index1&select_index2]
        final_data = current_array.data[select_index1&select_index2]

        final_array = coo_matrix((final_data, (final_row-row_start, final_col-col_start)), 
                                shape = (row_end-row_start,col_end-col_start),dtype=np.float32)
        final_array = final_array.toarray()
        if self.fill_diagonal_zero:
            #make sure it is located in the middle
            if row_start==col_start:
                np.fill_diagonal(final_array,0)
        if self.locus_embedding:
            actual_window_width = final_array.shape[1]
            expect_window_width = self.window_width
            actual_col_left = col_middle_point - col_start #left part size of the current window
            actual_col_start = expect_window_width//2 - actual_col_left
            current_count = np.sum(final_array)
            submat[0,0:row_end-row_start,actual_col_start:actual_col_start+actual_window_width] = final_array
        else:
            submat[0,0:row_end-row_start,0:col_end-col_start] = final_array
        input = np.nan_to_num(submat)
        if self.max_cutoff is not None:
            input = np.minimum(input,self.max_cutoff)
            max_value = self.max_cutoff
        else:
            max_value = np.max(input)
        input = np.log10(input+1)
        max_value = np.log10(max_value+1)
        input = self.convert_rgb(input,max_value)
        if self.transform is not None:
            input = self.transform(input)

        # === NEW: Load sequence data if available ===
        sequence_data = None
        if 'sequence_data' in self.data[chrom].__dict__:
            sequence_data = np.nan_to_num(self.data[chrom].__dict__['sequence_data']).astype(np.float32)
            sequence_data = torch.from_numpy(sequence_data)
            
        return input, self.total_count, [chrom, row_record_start, col_record_start], sequence_data