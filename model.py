import torch 
import torch.nn as nn
import math

class InputEmbeddings(nn.Module):
    
    def __init__(self,d_model:int , vocab_size : int ):
         super().__init__()
         self.d_model= d_model
         self.vocab_size = vocab_size 
         self.embedding = nn.Embedding(vocab_size , d_model)
         
    def forward(self ,x):
        return self.embedding(x)*math.sqrt(self.d_model)
    
## maximum length of words sentence is sequence length 

class PositionalEmbeddings(nn.Module):
    
    def __init__(self, d_model: int, seq_len : int ,dropout :float)->None:
        super().__init__()
        self.d_model = d_model
        self.seq_len = seq_len
        self.dropout = nn.Dropout(dropout)

    #Create a matrix of shape (seq_len ; d_model)
        pe = torch.zeros(seq_len, d_model)
        ## Create a vector of shape(Seq_len,1)
        position  = torch.arange(0,seq_len, dtype = torch.float).unsqueeze(1)  ## The torch.unsqueeze() function adds a dimension of size 1 at a specified position in a tensor’s shape.
        div_term  = torch.exp(torch.arange(0,d_model,2).float() * (-math.log(10000.0)/d_model)) ## slightly modified
        ## aAplly the sin to even postion 
        pe[:, 0::2] = torch.sin(position*div_term)
        pe[: ,1::2] = torch.cos(position*div_term)
        
        pe = pe.unsqueeze(0) ## (1,seq_len,d_model)
        
        ## when you have a tensor that you want to keep inside the module
        ## not as a parameter but you want it to be saved when you saved the file of the module 
         ## use register_buffer 
        self.register_buffer('pe' , pe)                
        
    def forward(self ,x ):
        x =x  + (self.pe[: , :x.shape[1], :]).requires_grad(False)   ## adding positional encoding + word embedding 
        return self.dropout(x)   ## drops some values so that model does not depend on specific neurons  It is a regularization technique
    
        
# requires_grad_(False)
# This disables gradient computation for the positional encodings:

# Positional encodings are fixed (precomputed sine/cosine values), not learnable.

# You don't want gradients to flow through them during backpropagation.
        
class LayerNormalisation(nn.Module):
    
    def __init__(self,eps:float=10**-6)-> None:
        super().__init__()
        self.eps = eps 
        self.alpha = nn.Parameter(torch.ones(1)) ## multiplied
        self.bias  = nn.Parameter(torch.ones(1)) ## added 
        
    def forward(self, x):
        mean = x.mean(dim = -1, keepdim=True)  ## keepdim =True it will not change the dimension of the vector . else it will be 1d vector 
        #Let’s use shape [2, 3, 4] for clarity:
        #2 batches
        #3 sequences per batch
        # 4 features per sequence  
        #Shape of x is [2, 3, 4]
        # Shape of mean becomes [2, 3, 1] ## mean across every word embedding 
        # Each [1x4] row becomes a single mean value.
        std = x.std(dim=-1,keepdim=True)
        return self.alpha *(x-mean)/(math.sqrt(std + self.eps)) + self.bias 
    
class FeedForwardBlock(nn.Module):
    
    def __init__(self, d_model:int , d_ff: int, dropout : float)->None:
        super().__init__()
        self.linear_1 = nn.Linear(d_model, d_ff) ## W1 and B1   output = input @ W1.T + b1 
        self.dropout= nn.Dropout(dropout)
        self.linear_2 = nn.Linear(d_ff,d_model) ## W2 and B2
        
    def forward(self,x):
        ## Batch, seq_Len, d_model= --< (batch, Seq_Len , d_fff) --> (batch , Seq_len , d_model):
        return self.linear_2(self.dropout(torch.relu(self.linear_1(x))))
        
        
class MultiHeadAttention(nn.Module):
    
    def __init__(self,d_model: int, h : int , dropout:float)->None:
        super().__init__()
        self.h = h ## No of attention heads
        assert d_model % h==0 , "d_model is not divisible by h "
        
        self.d_k = d_model // h 
        self.w_q = nn.Linear(d_model,d_model)  ## Wq 
        self.w_k = nn.Linear(d_model,d_model)  ## Wk
        self.w_v =  nn.Linear(d_model,d_model) ## Wv
        
        self.w_o = nn.Linear(d_model , d_model)## wo
        self.dropout = nn.Dropout(dropout)
    @staticmethod
    def attention(query,key,value,mask,dropout : nn.Dropout):
        d_k = query.shape[-1]
        # (Batch, h , seq_len , d_k)--> (Batch,h, seq_len , seq_len)
        attention_scores = (query @ key.transpose(-2,-1))/math.sqrt(d_k)## @ means multiplication of matrix 
        ## Applying mask 
        if mask is not None:
            attention_scores.masked_fill(mask==0 , -1e9)
        
        attention_scores = attention_scores.softmax(dim=-1) ## (batch,h,seq_len,seq_len)
        if dropout is not None : 
            attention_scores = dropout(attention_scores)
            
        return (attention_scores @value), attention_scores  #(batch, h,Seq_len ,d_k)
    def forward(self,q , k , v,mask):
        query = self.w_q(q)  ## (Batch,Seq_len,d_model)--> (batch,seq_len,d_model)
        key = self.w_k(k)      ## (Batch,Seq_len,d_model)--> (batch,seq_len,d_model)
        value = self.w_v(v)     ## (Batch,Seq_len,d_model)--> (batch,seq_len,d_model)
        ## Reshaping query, key  ,value matrix,  across d_model
        ## (Batch,Seq-len, d_model) --> (Batch,Seq_len,h,d_k)--> (batch, h,Seq_len ,d_k);
        
        query = query.view(query.shape[0] , query.shape[1],self.h,self.d_k).transpose(1,2)
        key = key.view(key.shape[0] , key.shape[1],self.h,self.d_k).transpose(1,2)
        value = value.view(value.shape[0],value.shape[1],self.h , self.d_k).transpose(1,2)
        
        x , self.attention_scores = MultiHeadAttention.attention(query,key,value,self.dropout)
        
        # (batcn,h , Seq_len, d _k) --> (Batch,Sq_len, h,d_k)
        x = x.transpose(1,2) 
        #(Batch,Sq_len, h,d_k)--> (Batch,Seq_Len,d_model)
        x = x.contiguous().view(x.shape[0],x.shape[1],self.h * self.d_k)
        
        # (Batch,Seq_Len,d_model)-->(Batch,seq_len,d_models)
        return self.w_o(x)

class ResidualConnection(nn.Module):
    
    def __init__(self , dropout:float)->None:
        super().__init__()
        self.dropout = nn.Dropout(dropout)
        self.norm = LayerNormalisation()      
        
    def forward(self,x ,sublayer):
        return x + self.dropout(sublayer(self.norm(x)))
     
class EncoderBlock(nn.Module):
    
    def __init__(self,self_attention_block : MultiHeadAttention ,feed_forward_block : FeedForwardBlock , dropout:float)->None:
        super().__init__()
        self.self_attention_block = self_attention_block
        self.feed_forward_block =feed_forward_block
        self.residual_connections = nn.ModuleList([ResidualConnection(dropout) for __i in range(2)])        

    def forward(self,x , src_mask):   ##mask appplied input of encoder we dont want padding words to intercat with other words
        x = self.residual_connections[0](x, lambda x : self.self_attention_block(x ,x ,x,src_mask))
        x = self.residual_connections[1](x , self.feed_forward_block)       
        return x  
    
class Encoder(nn.Module):
    
    def __init__(self,layers: nn.ModuleList)->None:
        super().__init__()
        self.layers =layers
        self.norm= LayerNormalisation()
        
    def forward(self ,x , mask):
        for layer in self.layers:
            x = layer(x, mask)
        return self.norm(x)


class DecoderBlock(nn.Module):
    
    def __init__(self,self_attention_block : MultiHeadAttention, cross_attention_block : MultiHeadAttention , feed_forward_block : FeedForwardBlock, dropout:float)->None:
        super().__init__()
        self.self_attention_block = self_attention_block
        self.cross_attention_block = cross_attention_block
        self.feed_forward_block = feed_forward_block 
        
        self.residual_connections = nn.ModuleList   [(ResidualConnection(dropout) for __ in range(3))]
    
    def forward(self, x , encoder_output , src_mask , tgt_mask):  ## two mask  one coming for encoder and one coming for decoder 
         x  = self.residual_connections[0](x , lambda x : self.self_attention_block(x, x,x , tgt_mask))
         x  = self.residual_connections[1](x , lambda x : self.cross_attention_block(x, encoder_output, encoder_output,src_mask))
         x  = self.residual_connections[2](x, self.feed_forward_block)
         return x
     
class Decoder(nn.Module):
     
    def __init__(self, layers : nn.ModuleList)-> None:
        super().__init__()
        self.layers = layers
        self.norm =  LayerNormalisation()
        
        
    def forward(self , x , encoder_output, src_mask , tgt_mask):
        for layer in self.layers:
           x = layer(x , encoder_output , src_mask , tgt_mask)
        return self.norm(x)
        
        
class ProjectionLayer(nn.Module):
    
    def __init__(self, d_model:int , vocab_size: int)-> None:
        super().__init__()
        self.proj = nn.Linear(d_model , vocab_size)
        
    def forward(self, x):
        # (Batch,Seq_len , d_model) --> (Batch , seq_len, vocab_size )
        return torch.log_softmax(self.proj(x), dim=-1)
    

class Transformer(nn.Module):
    
    def __init__(self, encoder : Encoder,decoder: Decoder , src_embed : InputEmbeddings, tgt_embed : InputEmbeddings,src_pos : PositionalEmbeddings , tgt_pos : PositionalEmbeddings,projection_layer : ProjectionLayer)-> None:
        super().__init__()
        self.encoder = encoder
        self.decoder = decoder  
        self.src_embed = src_embed 
        self.tgt_embed = tgt_embed
        self.src_pos = src_pos
        self.tgt_pos = tgt_pos
        self.projection_layer = projection_layer
    
    ## Three methods to encode, decode , project
    
    def encode(self, src , src_mask):
        src = self.src_embed(src)
        src = self.src_pos(src)
        return self.encoder(src,src_mask)
    
    def decode(self, encoder_output, src_mask, tgt, tgt_mask):
        tgt = self.tgt_embed(tgt)
        tgt = self.tgt_pos(tgt)
        return self.decoder(tgt, encoder_output,src_mask,tgt_mask)
         
    def project(self, x):
        return self.projection_layer(x)
    
    

def build_transformer(src_vocab_size : int, tgt_vocab_size: int, src_seq_len : int, tgt_seq_len : int, d_model : int = 512, N : int = 6 , h :int =8 , dropout :float=0.1,d_ff: int = 2048):
    ## Creating embedding layers 
    
    src_embed = InputEmbeddings(d_model, src_vocab_size)
    tgt_embed = InputEmbeddings(d_model , tgt_vocab_size)
    
    ## Creating pos encoding layers 
    
    src_pos = PositionalEmbeddings(d_model , src_seq_len, dropout)
    tgt_pos = PositionalEmbeddings(d_model , tgt_seq_len, dropout)
    
    #Encoder block  
    encoder_blocks =[]
    
    for _ in range(6):
        encoder_self_attention_block = MultiHeadAttention(d_model,h,dropout)
        feed_forward_block = FeedForwardBlock(d_model,d_ff, dropout)
        encoder_block = EncoderBlock(encoder_self_attention_block,feed_forward_block , dropout)
        encoder_blocks.append(encoder_block)
        
    # Decoder block 
    decoder_blocks= []
    for _ in range(6):
        decoder_self_attention_block = MultiHeadAttention(d_model,h,dropout)
        decoder_cross_attention_block = MultiHeadAttention(d_model,h, dropout)
        feed_forward_block = FeedForwardBlock(d_model , d_ff, dropout)
        decoder_block = DecoderBlock(decoder_self_attention_block,decoder_cross_attention_block,feed_forward_block,dropout)
        decoder_blocks.append(decoder_block)
        
        
    ## Create encoder and decoder 
    
    encoder = Encoder(nn.ModuleList(encoder_blocks))
    decoder = Decoder(nn.ModuleList(decoder_blocks))
    
    ## Projection layer
    projection_layer = ProjectionLayer(d_model,tgt_vocab_size)
    ## Transformer 
    transformer = Transformer(encoder, decoder, src_embed,tgt_embed,src_pos,tgt_pos, projection_layer)
      
    # Initialize parameters 
    
    for p in transformer.parameters():
        if p.dim()>1:
            nn.init.xavier_uniform_(p)
        
    return transformer